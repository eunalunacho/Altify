import time
import subprocess
import requests

# 설정
RABBITMQ_API = "http://localhost:15672/api/queues/%2F/alt_generation_queue"
AUTH = ('altify', 'altify2025')
MAX_WORKERS = 2  # 최대 워커 수 (GPU 제한 때문)
MIN_WORKERS = 1

def get_queue_depth():
    """RabbitMQ API를 찔러서 현재 대기 중인 메시지 수를 가져옴"""
    try:
        res = requests.get(RABBITMQ_API, auth=AUTH)
        data = res.json()
        return data.get('messages', 0)
    except:
        return 0

def scale_workers(count):
    """Docker Compose 명령어로 워커 수 조절"""
    print(f"⚖️ 워커를 {count}개로 조정합니다...")
    # --scale 명령어를 서브프로세스로 실행
    subprocess.run(["docker", "compose", "up", "-d", "--scale", f"worker={count}", "--no-recreate"])

def main():
    current_workers = MIN_WORKERS
    
    while True:
        queue_count = get_queue_depth()
        print(f"📊 현재 대기열: {queue_count}개 / 현재 워커: {current_workers}개")

        # 로직: 대기열이 5개 초과(6개 이상)면 풀가동, 0개면 최소 유지
        target_workers = current_workers
        
        if queue_count > 5 and current_workers < MAX_WORKERS:
            target_workers = MAX_WORKERS
        elif queue_count == 0 and current_workers > MIN_WORKERS:
            target_workers = MIN_WORKERS
            
        # 변경이 필요할 때만 명령어 실행
        if target_workers != current_workers:
            scale_workers(target_workers)
            current_workers = target_workers
            
        time.sleep(5)  # 5초마다 검사

if __name__ == "__main__":
    main()