import torch
from transformers import (
    AutoProcessor,
    LlavaForConditionalGeneration,
    BitsAndBytesConfig
)
from PIL import Image
from typing import Optional
import logging
import time

logger = logging.getLogger(__name__)


class LLaVAModelLoader:
    """Singleton 패턴을 사용한 LLaVA 모델 로더"""
    
    _instance = None
    _model = None
    _processor = None
    _is_loaded = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLaVAModelLoader, cls).__new__(cls)
        return cls._instance
    
    def load(self):
        """모델을 GPU에 로드 (4-bit 양자화 적용)"""
        if self._is_loaded:
            logger.info("모델이 이미 로드되어 있습니다.")
            return
        
        model_id = "llava-hf/llava-1.5-7b-hf"
        logger.info("[1/4] LLaVA 로딩 시작: %s", model_id)

        try:
            # 1) Processor
            logger.info("[2/4] Processor 다운로드/로딩 시작")
            t0 = time.time()
            self._processor = AutoProcessor.from_pretrained(model_id)
            logger.info("[2/4] Processor 로딩 완료 (%.1fs)", time.time() - t0)

            # 2) Quantization config (이건 빠름)
            logger.info("[3/4] 4-bit 양자화 설정 생성")
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.float16
            )
            logger.info("[3/4] 양자화 설정 생성 완료")

            # 3) Model (여기가 오래 걸림)
            logger.info("[4/4] Model 다운로드/로딩 시작 (수 분 걸릴 수 있음)")
            t1 = time.time()
            self._model = LlavaForConditionalGeneration.from_pretrained(
                model_id,
                quantization_config=quantization_config,
                device_map="auto",
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True
            )
            logger.info("[4/4] Model 로딩 완료 (%.1fs)", time.time() - t1)

            self._is_loaded = True
            logger.info("🎉 전체 모델 로딩 완료!")
                
        except Exception as e:
            logger.error(f"모델 로딩 실패: {str(e)}", exc_info=True)
            raise
    
    def _resize_for_llava(self, image: Image.Image, max_side: int = 896) -> Image.Image:
        """너무 큰 이미지는 강제 축소해서 GPU/드라이버 리셋(TDR) 방지"""
        w, h = image.size
        m = max(w, h)
        if m <= max_side:
            return image
        scale = max_side / float(m)
        new_w = int(w * scale)
        new_h = int(h * scale)
        return image.resize((new_w, new_h), Image.BICUBIC)

    def generate_caption(self, image: Image.Image, context: str, temperature: float = 0.7, prompt_variant: int = 1) -> str:
        """
        이미지와 문맥을 기반으로 ALT 텍스트 생성
        
        Args:
            image: PIL Image 객체
            context: 문맥 텍스트
            temperature: 생성 온도 (다양성 조절)
            prompt_variant: 프롬프트 변형 (1 또는 2)
        
        Returns:
            생성된 ALT 텍스트
        """
        if not self._is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다. load()를 먼저 호출하세요.")
        
        # 이미지 리사이즈 
        image = self._resize_for_llava(image, max_side=896)  # 768~1024 사이로 조절 추천

        context_block = f"Context (supporting hint, do not quote): {context}"
        prompt_common = (
            "Task Context\n"
            "You are an AI assistant that writes ALT text for web accessibility.\n"
            "Your task is to generate a single-sentence ALT text describing the given image.\n"
            "\n"
            "Background Details, Data Documents\n"
            "- Input consists of:\n"
            "  (1) an image\n"
            "  (2) an accompanying text (context) written by a human.\n"
            "- The image is the primary source of truth.\n"
            "- The context is only a supporting hint and must NOT be quoted or copied.\n"
            "- Never complete the sentence based primarily on the context.\n"
            "- Use the context only to add nuance (place/situation) IF it matches what is visible.\n"
            "\n"
            "Examples (Few-Shot Prompting)\n"
            "Good examples:\n"
            "- \"버스 정류장 근처 인도에 벚꽃이 핀 나무가 줄지어 서 있다.\"\n"
            "- \"나무 탁자 위에 노트북이 열려 있고 옆에 머그컵이 놓여 있다.\"\n"
            "\n"
            "Bad examples:\n"
            "- Copying or quoting the context text\n"
            "- Adding guesses (e.g., snow, emotions, events) not visually confirmed\n"
            "- Adding headers/labels such as [문맥], [이미지설명], ALT:, etc.\n"
            "\n"
            "Detailed List of Tasks\n"
            "1. Describe ONLY what is visually observable in the image.\n"
            "2. Use the context only as a minor hint (no quoting), and only within visually confirmed range.\n"
            "3. Write exactly ONE natural Korean sentence.\n"
            "4. Include subject + action/state + background when possible.\n"
            "\n"
            "Important Guidelines\n"
            "- Output must be natural Korean.\n"
            "- No exaggeration, no emotions, no interpretation, no guessing.\n"
            "- Do NOT use speculative phrases like \"~인 듯\", \"~같다\", \"아마\".\n"
            "- Do NOT include any meta text, explanations, or labels.\n"
            "- Output ONLY the final ALT sentence.\n"
            "\n"
            "Output Formatting\n"
            "- One Korean sentence only.\n"
            "- No line breaks.\n"
            "- No quotes.\n"
            "- No prefixes.\n"
        )
        
        # 프롬프트 변형 (다양한 관점의 ALT 생성)
        if prompt_variant == 1:
            prompt = (
                f"{prompt_common}"
                "USER: <image>\n"
                f"{context_block}\n"
                "\n"
                "[Follow all the instructions above strictly.]\n"
                "Output requirement: ONE Korean sentence including subject/action(or state)/background.\n"
                "ASSISTANT:"
            )
        else:
            prompt = (
                f"{prompt_common}"
                "USER: <image>\n"
                f"{context_block}\n"
                "\n"
                "[Follow all the instructions above strictly.]\n"
                "Output requirement: ONE Korean sentence, as short and essentially as possible.\n"
                "ASSISTANT:"
            )
                
        # 입력 처리 및 텐서를 모델 디바이스로 이동
        inputs = self._processor(
            text=prompt,
            images=image,
            return_tensors="pt"
        ).to(self._model.device)
        
        # 생성 파라미터 설정 (메모리 효율성을 위해 제한)
        generation_config = {
            "max_new_tokens": 60,
            "do_sample": False,
            "num_beams": 1,
            "repetition_penalty": 1.1,
            "pad_token_id": self._processor.tokenizer.eos_token_id,
            "eos_token_id": self._processor.tokenizer.eos_token_id,
        }
        

        try:
        # 추론 수행
            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs,
                    **generation_config
                )
        
        
            # 결과 디코딩
            # 입력 프롬프트 길이
            prompt_len = inputs["input_ids"].shape[-1]

            # 모델이 새로 생성한 토큰만 분리
            new_tokens = generated_ids[:, prompt_len:]

            # 디코딩
            generated_text = self._processor.batch_decode(
                new_tokens,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0].strip()

            # 줄바꿈/라벨 제거 
            generated_text = generated_text.replace("\n", " ").strip()

            # 한 문장만 남기기(마침표/물음표/느낌표 기준으로 첫 문장)
            for sep in ["。", ".", "!", "?", "！", "？"]:
                if sep in generated_text:
                    generated_text = generated_text.split(sep)[0].strip() + ("." if sep == "." else "")
                    break

            return generated_text
        
        except torch.cuda.OutOfMemoryError:
            # ✅ OOM 안전 처리
            torch.cuda.empty_cache()
            raise RuntimeError("GPU 메모리 부족으로 생성에 실패했습니다.")  
    
    def generate_captions(self, image: Image.Image, context: str) -> tuple[str, str]:
        """
        이미지와 문맥을 기반으로 2개의 ALT 텍스트 후보 생성
        
        Args:
            image: PIL Image 객체
            context: 문맥 텍스트
        
        Returns:
            (첫 번째 ALT, 두 번째 ALT) 튜플
        """
        # 첫 번째 ALT: 기본 temperature (0.7)
        alt1 = self.generate_caption(image, context, temperature=0.7, prompt_variant=1)
        
        # 두 번째 ALT: 더 높은 temperature (0.9)로 다양성 증가, 다른 프롬프트 사용
        alt2 = self.generate_caption(image, context, temperature=0.9, prompt_variant=2)
        
        return (alt1, alt2)
    
    @property
    def model(self):
        """모델 인스턴스 반환"""
        if not self._is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        return self._model
    
    @property
    def processor(self):
        """Processor 인스턴스 반환"""
        if not self._is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        return self._processor


# 전역 인스턴스
model_loader = LLaVAModelLoader()

