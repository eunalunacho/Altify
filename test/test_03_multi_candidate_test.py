# test/test_03_multi_candidate_test.py
"""다중 후보 생성 테스트"""
import statistics
from test_common import upload_task, wait_for_task_completion

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    print("Warning: sentence_transformers not available. Similarity check will be skipped.")


def test_multiple_candidates(num_tests: int = 5):
    """
    1. 2개 이상의 후보 생성 확인
    2. 후보 간 차이 확인 (유사도 < 0.9)
    
    Args:
        num_tests: 테스트 케이스 개수 (기본값: 5, 실제 환경에서는 더 많이)
    """
    test_cases = [
        {'context': '친환경 소재로 만든 가방을 들고 있는 여성'},
        {'context': '도심 속 카페 인테리어, 나무 테이블과 식물'},
        {'context': '해변가에서 일몰을 배경으로 한 사진'},
        {'context': '현대적인 사무실 공간, 스탠딩 데스크와 모니터'},
        {'context': '산 정상에서 바라본 풍경, 구름과 나무들'},
    ][:num_tests]
    
    # 유사도 계산 모델 (선택사항)
    similarity_model = None
    if HAS_SENTENCE_TRANSFORMERS:
        try:
            similarity_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        except Exception as e:
            print(f"Warning: Failed to load similarity model: {e}")
    
    results = []
    
    for i, case in enumerate(test_cases, 1):
        print(f"Test case {i}/{len(test_cases)}: {case['context'][:30]}...")
        
        try:
            # 업로드 및 완료 대기
            upload_result = upload_task(context=case['context'])
            task_id = upload_result['id']
            
            task = wait_for_task_completion(task_id, timeout=300)
            
            alt1 = task.get('alt_generated_1')
            alt2 = task.get('alt_generated_2')
            
            # 기본 검증
            assert alt1 is not None, "alt_generated_1 is None"
            assert alt2 is not None, "alt_generated_2 is None"
            assert alt1 != alt2, "alt1 and alt2 are identical"
            
            # 유사도 계산 (선택사항)
            similarity = None
            if similarity_model and alt1 and alt2:
                try:
                    embeddings = similarity_model.encode([alt1, alt2])
                    similarity = float(np.dot(embeddings[0], embeddings[1]) / (
                        np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
                    ))
                except Exception as e:
                    print(f"  Warning: Similarity calculation failed: {e}")
            
            results.append({
                'task_id': task_id,
                'alt1': alt1,
                'alt2': alt2,
                'similarity': similarity,
                'different': similarity < 0.9 if similarity is not None else True
            })
            
            print(f"  ✓ ALT 1: {alt1[:50]}...")
            print(f"  ✓ ALT 2: {alt2[:50]}...")
            if similarity is not None:
                print(f"  ✓ Similarity: {similarity:.3f}")
        
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results.append({
                'error': str(e),
                'success': False
            })
    
    # 결과 집계
    successful_tests = [r for r in results if 'error' not in r]
    all_have_2_candidates = len(successful_tests) == len(test_cases)
    
    similarities = [r['similarity'] for r in successful_tests if r.get('similarity') is not None]
    avg_similarity = statistics.mean(similarities) if similarities else None
    
    all_different = all(
        r.get('similarity', 0) < 0.9 if r.get('similarity') is not None else True
        for r in successful_tests
    )
    
    result = {
        'success': all_have_2_candidates and (all_different if similarities else True),
        'total_tests': len(test_cases),
        'successful_tests': len(successful_tests),
        'all_have_2_candidates': all_have_2_candidates,
        'avg_similarity': avg_similarity,
        'all_different': all_different if similarities else 'N/A (similarity model not available)',
        'results': results
    }
    
    print(f"\n✓ Multi-Candidate Test: {len(successful_tests)}/{len(test_cases)} succeeded")
    print(f"  All have 2 candidates: {all_have_2_candidates}")
    if avg_similarity is not None:
        print(f"  Average similarity: {avg_similarity:.3f}")
        print(f"  All different (similarity < 0.9): {all_different}")
    
    return result


if __name__ == '__main__':
    result = test_multiple_candidates(3)  # 테스트용으로 3개만
    print("\nResult:", result)
