import axios from 'axios';

const client = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터
client.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 응답 인터셉터
client.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // 서버 응답이 있는 경우
      const status = error.response.status;
      const message = error.response.data?.detail || '서버 오류가 발생했습니다.';
      
      if (status === 500) {
        alert(`서버 연결 오류: ${message}`);
      } else if (status === 422) {
        alert(`입력 데이터 오류: ${message}`);
      } else {
        alert(`오류 발생: ${message}`);
      }
    } else if (error.request) {
      // 요청은 보냈지만 응답을 받지 못한 경우
      alert('서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.');
    } else {
      // 요청 설정 중 오류 발생
      alert(`요청 오류: ${error.message}`);
    }
    
    return Promise.reject(error);
  }
);

export default client;

