# test/test_04_hardware_test.py
"""하드웨어 제약 테스트 (6GB VRAM)"""
import subprocess
import sys
from pathlib import Path

# worker 모듈 import (컨테이너 내부와 호스트 환경 모두 지원)
import os

HAS_WORKER_MODULES = False
worker_src_path = None

try:
    # 컨테이너 내부와 호스트 환경 구분
    # 컨테이너 내부: /app/src에 worker 소스가 있음
    # 호스트: ../worker/src에 worker 소스가 있음
    
    # 1. 컨테이너 내부 경로 확인
    if os.path.exists('/app/src'):
        container_model_path = Path('/app/src/core/model.py')
        if container_model_path.exists():
            # 컨테이너 내부에서 실행 중
            worker_src_path = Path('/app/src')
            sys.path.insert(0, str(worker_src_path))
        else:
            # /app/src는 존재하지만 core/model.py가 없음
            raise ImportError(f"/app/src exists but core/model.py not found at {container_model_path}")
    else:
        # 호스트 환경에서 실행 중
        test_file_path = Path(__file__).resolve()
        worker_src_path = test_file_path.parent.parent / 'worker' / 'src'
        if not worker_src_path.exists():
            raise ImportError(f"Worker source path not found: {worker_src_path}")
        sys.path.insert(0, str(worker_src_path))
    
    # 2. 경로 확인 후 import 시도
    # 먼저 torch와 PIL을 import (의존성 확인)
    import torch
    from PIL import Image
    
    # 3. core.model 모듈 import
    from core.model import model_loader
    
    HAS_WORKER_MODULES = True
except ImportError as e:
    HAS_WORKER_MODULES = False
    error_msg = str(e)
    print(f"Warning: Worker modules not available.")
    print(f"  Error: {error_msg}")
    if worker_src_path:
        print(f"  Tried path: {worker_src_path}")
        if worker_src_path.exists():
            print(f"  Path exists: Yes")
            model_file = worker_src_path / 'core' / 'model.py'
            print(f"  core/model.py exists: {model_file.exists()}")
        else:
            print(f"  Path exists: No")
    else:
        print(f"  Could not determine worker source path")
    print("  This test should run inside worker container or have worker/src in the project root.")
except Exception as e:
    HAS_WORKER_MODULES = False
    print(f"Warning: Unexpected error loading worker modules: {e}")
    import traceback
    traceback.print_exc()


def get_gpu_memory_mb():
    """GPU 메모리 사용량 조회 (MB 단위)"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,nounits,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip().split('\n')[0])
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError, IndexError):
        return None


def create_test_image():
    """테스트용 더미 이미지 생성"""
    if not HAS_WORKER_MODULES:
        return None
    
    # 간단한 테스트 이미지
    img = Image.new('RGB', (224, 224), color='red')
    return img


def test_6gb_vram_operation():
    """
    1. 모델 로드 시 GPU 메모리 사용량 측정
    2. 추론 중 메모리 사용량 모니터링
    3. OOM 발생 여부 확인
    """
    if not HAS_WORKER_MODULES:
        return {
            'success': False,
            'error': 'Worker modules not available. Run this test inside worker container.',
            'skipped': True
        }
    
    initial_memory = get_gpu_memory_mb()
    if initial_memory is None:
        return {
            'success': False,
            'error': 'Failed to get GPU memory info. nvidia-smi may not be available.',
            'skipped': True
        }
    
    print(f"Initial GPU memory: {initial_memory} MB")
    
    try:
        # 모델 로드
        print("Loading model...")
        model_loader.load()
        after_load_memory = get_gpu_memory_mb()
        if after_load_memory is None:
            return {'success': False, 'error': 'Failed to get memory after load'}
        
        load_memory_usage = after_load_memory - initial_memory
        print(f"Memory after model load: {after_load_memory} MB (+{load_memory_usage} MB)")
        
        # 10회 연속 추론 테스트
        print("Running 10 inference tests...")
        oom_count = 0
        max_memory_during_inference = after_load_memory
        
        test_image = create_test_image()
        
        for i in range(10):
            try:
                # 추론 수행
                alt1, alt2 = model_loader.generate_captions(
                    image=test_image,
                    context="테스트 문맥"
                )
                
                # 메모리 확인
                current_memory = get_gpu_memory_mb()
                if current_memory:
                    max_memory_during_inference = max(max_memory_during_inference, current_memory)
                
                # 메모리 정리
                torch.cuda.empty_cache()
                
                print(f"  ✓ Inference {i+1}/10 completed")
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower() or "OOM" in str(e):
                    oom_count += 1
                    torch.cuda.empty_cache()
                    print(f"  ✗ OOM at inference {i+1}/10")
                else:
                    raise
        
        peak_memory_usage = max_memory_during_inference - initial_memory
        total_memory_usage = after_load_memory - initial_memory
        
        # 성공 기준: OOM 없음, 총 메모리 < 6GB
        success = (oom_count == 0 and total_memory_usage < 6 * 1024)
        
        result = {
            'success': success,
            'initial_memory_mb': initial_memory,
            'after_load_memory_mb': after_load_memory,
            'load_memory_usage_mb': load_memory_usage,
            'peak_memory_during_inference_mb': max_memory_during_inference,
            'peak_memory_usage_mb': peak_memory_usage,
            'total_memory_usage_mb': total_memory_usage,
            'oom_count': oom_count,
            'oom_rate': oom_count / 10,
            'under_6gb': total_memory_usage < 6 * 1024
        }
        
        print(f"\n✓ Hardware Test Results:")
        print(f"  Model load memory: {load_memory_usage:.0f} MB")
        print(f"  Peak inference memory: {peak_memory_usage:.0f} MB")
        print(f"  Total memory usage: {total_memory_usage:.0f} MB")
        print(f"  OOM count: {oom_count}/10")
        print(f"  Under 6GB: {result['under_6gb']}")
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


if __name__ == '__main__':
    result = test_6gb_vram_operation()
    print("\nResult:", result)
