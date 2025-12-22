import { useState } from 'react';
import BlogEditor from './components/BlogEditor';
import UploadForm from './components/UploadForm';
import StatusDashboard from './components/StatusDashboard';
import ReviewPanel from './components/ReviewPanel';

function App() {
  const [currentTask, setCurrentTask] = useState(null);
  const [uploadedImage, setUploadedImage] = useState(null);
  const [view, setView] = useState('blog'); // 'blog', 'upload', 'status', 'review'

  const handleBlogPublishSuccess = (tasks) => {
    // 블로그 발행 성공 - BlogEditor에서 자체적으로 상태 관리하므로 여기서는 별도 처리 불필요
    console.log('블로그 발행 완료:', tasks);
  };

  const handleUploadSuccess = (taskData) => {
    setCurrentTask(taskData);
    setView('status');
  };

  const handleStatusChange = (taskData) => {
    setCurrentTask(taskData);
    
    if (taskData.status === 'DONE') {
      // 이미지 URL 생성 (MinIO에서 가져와야 하지만, 현재는 임시로 처리)
      // 실제로는 백엔드에서 이미지 URL을 제공하거나 MinIO 직접 접근
      const imagePath = taskData.image_path;
      // MinIO URL 생성 (실제 환경에 맞게 수정 필요)
      const imageUrl = `http://localhost:9000/${imagePath}`;
      setUploadedImage(imageUrl);
      setView('review');
    } else if (taskData.status === 'FAILED') {
      alert('작업 처리 중 오류가 발생했습니다. 다시 시도해주세요.');
      setView('upload');
      setCurrentTask(null);
      setUploadedImage(null);
    }
  };

  const handleApprovalSuccess = () => {
    // 승인 완료 후 초기화
    alert('작업이 완료되었습니다!');
    setView('upload');
    setCurrentTask(null);
    setUploadedImage(null);
  };

  const handleReset = () => {
    setView('blog');
    setCurrentTask(null);
    setUploadedImage(null);
  };

  return (
    <div className="min-h-screen">
      {/* 헤더 */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-primary-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-xl">A</span>
              </div>
              <h1 className="text-2xl font-bold text-gray-800">Altify</h1>
            </div>
            <p className="text-sm text-gray-600 hidden sm:block">
              ALT 텍스트 생성 플랫폼
            </p>
            {view !== 'blog' && (
              <button
                onClick={handleReset}
                className="px-4 py-2 text-primary-600 hover:text-primary-700 font-medium transition-colors"
              >
                새 작업 시작
              </button>
            )}
          </div>
        </div>
      </header>

      {/* 메인 컨텐츠 */}
      <main className="py-8">
        {view === 'blog' && (
          <BlogEditor onPublishSuccess={handleBlogPublishSuccess} />
        )}

        {view === 'upload' && (
          <UploadForm onUploadSuccess={handleUploadSuccess} />
        )}

        {view === 'status' && currentTask && (
          <StatusDashboard
            taskId={currentTask.id}
            onStatusChange={handleStatusChange}
          />
        )}

        {view === 'review' && currentTask && uploadedImage && (
          <ReviewPanel
            task={currentTask}
            imageUrl={uploadedImage}
            onApprovalSuccess={handleApprovalSuccess}
          />
        )}
      </main>

      {/* 푸터 */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-600">
            © 2025 Altify.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;

