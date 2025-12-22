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

            # 3) Quantization config 
            logger.info("[3/4] 4-bit 양자화 설정 생성")
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.float16
            )
            logger.info("[3/4] 양자화 설정 생성 완료")

            # 4) Model
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
    
    def _resize_for_llava(self, image: Image.Image, max_side: int = 672) -> Image.Image:
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
        image = self._resize_for_llava(image, max_side=672)  

        context_block = f"Context (supporting hint, do not quote): {context}"
        prompt_common = (
            "Task Context\n"
            "You are an AI assistant that writes ALT text for web accessibility.\n"
            "Your task is to generate a single-sentence ALT text describing the given image.\n"
            "\n"
            "Background Details, Data Documents\n"
            "- Input consists of:\n"
            "  (1) an image\n"
            "  (2) keywords extracted from text written by a human.\n"
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
        # temperature가 0.5 이상일 때만 do_sample=True로 설정 (그 외는 greedy decoding)
        use_sampling = temperature >= 0.5
        generation_config = {
            "max_new_tokens": 60,
            "do_sample": use_sampling,
            "temperature": temperature if use_sampling else None,
            "num_beams": 1 if use_sampling else 1,
            "repetition_penalty": 1.1,
            "pad_token_id": self._processor.tokenizer.eos_token_id,
            "eos_token_id": self._processor.tokenizer.eos_token_id,
        }
        # do_sample이 False일 때 temperature 파라미터 제거
        if not use_sampling:
            generation_config.pop("temperature", None)
        

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
    
    def _is_alt_similar_to_context(self, alt_text: str, context: str) -> bool:
        """
        생성된 ALT 텍스트가 사용자 문맥의 일부와 동일한지 확인
        
        Args:
            alt_text: 생성된 ALT 텍스트
            context: 사용자가 작성한 원본 문맥 텍스트
        
        Returns:
            ALT가 문맥의 일부와 동일하면 True
        """
        if not alt_text or not context:
            return False
        
        # 공백 정리
        alt_clean = alt_text.strip()
        context_clean = context.strip()
        
        # ALT 텍스트가 문맥에 포함되어 있는지 확인
        if alt_clean in context_clean:
            return True
        
        # ALT 텍스트의 주요 부분(단어들)이 문맥에 포함되어 있는지 확인
        # ALT 텍스트를 단어로 분리하여 확인
        alt_words = alt_clean.split()
        if len(alt_words) >= 3:  # 3개 이상의 단어가 있으면
            # ALT 텍스트의 연속된 단어들이 문맥에 포함되어 있는지 확인
            for i in range(len(alt_words) - 2):
                phrase = ' '.join(alt_words[i:i+3])  # 3개 단어씩 묶어서 확인
                if phrase in context_clean:
                    return True
        
        return False
    
    def generate_captions(self, image: Image.Image, context: str) -> tuple[str, str]:
        """
        이미지와 문맥을 기반으로 2개의 ALT 텍스트 후보 생성
        
        Args:
            image: PIL Image 객체
            context: 문맥 텍스트
        
        Returns:
            (첫 번째 ALT, 두 번째 ALT) 튜플
        """
        # 이미지 복사본 생성 (두 번째 생성 시 원본 이미지 재사용 방지)
        import copy
        image_copy = copy.deepcopy(image)
        
        # 첫 번째 ALT: 낮은 temperature (0.2)로 안정적인 생성, greedy decoding 사용
        alt1 = self.generate_caption(image, context, temperature=0.2, prompt_variant=1)
        
        # 생성된 ALT가 문맥의 일부와 동일한지 확인하고 재생성
        max_context_retries = 3
        context_retry_count = 0
        while self._is_alt_similar_to_context(alt1, context) and context_retry_count < max_context_retries:
            logger.warning(f"ALT 1이 사용자 문맥과 유사합니다. 재생성 시도 {context_retry_count + 1}/{max_context_retries}")
            alt1 = self.generate_caption(image, context, temperature=0.3 + (context_retry_count * 0.1), prompt_variant=1)
            context_retry_count += 1
        
        # 두 번째 ALT: 첫 번째보다 약간 높은 temperature (0.3)로 다양성 증가, 다른 프롬프트 사용
        # 이미지 복사본 사용하여 첫 번째 생성의 영향 최소화
        # temperature 0.3은 0.5 미만이므로 greedy decoding 사용
        alt2 = self.generate_caption(image_copy, context, temperature=0.3, prompt_variant=2)
        
        # 생성된 ALT가 문맥의 일부와 동일한지 확인하고 재생성
        context_retry_count = 0
        while self._is_alt_similar_to_context(alt2, context) and context_retry_count < max_context_retries:
            logger.warning(f"ALT 2가 사용자 문맥과 유사합니다. 재생성 시도 {context_retry_count + 1}/{max_context_retries}")
            alt2 = self.generate_caption(image_copy, context, temperature=0.4 + (context_retry_count * 0.1), prompt_variant=2)
            context_retry_count += 1
        
        # 두 ALT가 동일한 경우 재생성 시도 (최대 2회)
        max_retries = 2
        retry_count = 0
        while alt1 == alt2 and retry_count < max_retries:
            logger.warning(f"ALT 1과 ALT 2가 동일합니다. 재생성 시도 {retry_count + 1}/{max_retries}")
            # temperature를 더 높여서 재생성
            alt2 = self.generate_caption(image_copy, context, temperature=0.5, prompt_variant=2)
            retry_count += 1
        
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

