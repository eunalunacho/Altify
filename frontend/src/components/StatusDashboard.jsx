import { useState, useEffect } from 'react';
import client from '../api/client';

const StatusDashboard = ({ taskId, onStatusChange }) => {
  const [task, setTask] = useState(null);
  const [isPolling, setIsPolling] = useState(true);

  useEffect(() => {
    if (!taskId) return;

    let pollInterval;

    const pollTaskStatus = async () => {
      try {
        const response = await client.get(`/tasks/${taskId}`);
        const taskData = response.data;
        
        setTask(taskData);

        // 상태가 DONE 또는 FAILED가 되면 폴링 중지
        if (taskData.status === 'DONE' || taskData.status === 'FAILED') {
          setIsPolling(false);
          if (onStatusChange) {
            onStatusChange(taskData);
          }
        }
      } catch (error) {
        console.error('상태 조회 오류:', error);
        setIsPolling(false);
      }
    };

    // 즉시 한 번 실행
    pollTaskStatus();

    // 3초마다 폴링
    if (isPolling) {
      pollInterval = setInterval(pollTaskStatus, 3000);
    }

    return () => {
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [taskId, isPolling, onStatusChange]);

  if (!task) {
    return (
      <div className="w-full max-w-4xl mx-auto p-6">
        <div className="bg-white rounded-lg shadow-lg p-8 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">작업 정보를 불러오는 중...</p>
        </div>
      </div>
    );
  }

  const getStatusMessage = () => {
    switch (task.status) {
      case 'PENDING':
        return '작업이 대기 중입니다...';
      case 'PROCESSING':
        return 'AI가 이미지를 분석 중입니다...';
      case 'DONE':
        return '분석이 완료되었습니다!';
      case 'FAILED':
        return '분석 중 오류가 발생했습니다.';
      default:
        return '처리 중...';
    }
  };

  const getStatusColor = () => {
    switch (task.status) {
      case 'PENDING':
        return 'text-yellow-600';
      case 'PROCESSING':
        return 'text-blue-600';
      case 'DONE':
        return 'text-green-600';
      case 'FAILED':
        return 'text-red-600';
      default:
        return 'text-gray-600';
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <div className="text-center">
          <div className="mb-6">
            {task.status === 'PROCESSING' || task.status === 'PENDING' ? (
              <div className="flex justify-center items-center space-x-4">
                <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-primary-600"></div>
                <div className="text-left">
                  <h3 className={`text-xl font-semibold ${getStatusColor()}`}>
                    {getStatusMessage()}
                  </h3>
                  <p className="text-gray-500 mt-2">
                    작업 ID: {task.id}
                  </p>
                </div>
              </div>
            ) : task.status === 'DONE' ? (
              <div className="space-y-4">
                <div className="flex justify-center">
                  <svg
                    className="h-16 w-16 text-green-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                </div>
                <h3 className={`text-xl font-semibold ${getStatusColor()}`}>
                  {getStatusMessage()}
                </h3>
                <p className="text-gray-500">작업 ID: {task.id}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex justify-center">
                  <svg
                    className="h-16 w-16 text-red-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                </div>
                <h3 className={`text-xl font-semibold ${getStatusColor()}`}>
                  {getStatusMessage()}
                </h3>
                <p className="text-gray-500">작업 ID: {task.id}</p>
              </div>
            )}
          </div>

          {task.status === 'PROCESSING' && (
            <div className="mt-8 bg-blue-50 rounded-lg p-4">
              <p className="text-blue-800 text-sm">
                💡 AI가 이미지를 분석하고 ALT 텍스트를 생성하고 있습니다.
                <br />
                잠시만 기다려주세요...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatusDashboard;

