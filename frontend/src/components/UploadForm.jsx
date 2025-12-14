import { useState, useRef } from 'react';
import client from '../api/client';

const UploadForm = ({ onUploadSuccess }) => {
  const [file, setFile] = useState(null);
  const [contextText, setContextText] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type.startsWith('image/')) {
      handleFileSelect(droppedFile);
    }
  };

  const handleFileSelect = (selectedFile) => {
    setFile(selectedFile);
    
    // 미리보기 생성
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreview(reader.result);
    };
    reader.readAsDataURL(selectedFile);
  };

  const handleFileInputChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      handleFileSelect(selectedFile);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      alert('이미지 파일을 선택해주세요.');
      return;
    }
    
    if (!contextText.trim()) {
      alert('문맥 텍스트를 입력해주세요.');
      return;
    }

    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('이미지', file);
      formData.append('문맥텍스트', contextText);

      const response = await client.post('/tasks/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      if (response.data && response.data.id) {
        onUploadSuccess(response.data);
      } else {
        throw new Error('응답 데이터가 올바르지 않습니다.');
      }
    } catch (error) {
      console.error('업로드 오류:', error);
      // 에러는 client.js의 인터셉터에서 처리됨
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveFile = () => {
    setFile(null);
    setPreview(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-800 mb-6 text-center">
          이미지 업로드
        </h2>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 드래그 앤 드롭 영역 */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-all ${
              isDragging
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-300 hover:border-primary-400'
            } ${preview ? 'border-solid' : ''}`}
          >
            {preview ? (
              <div className="relative">
                <img
                  src={preview}
                  alt="미리보기"
                  className="max-h-64 mx-auto rounded-lg shadow-md"
                />
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  className="mt-4 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                >
                  이미지 제거
                </button>
              </div>
            ) : (
              <div>
                <svg
                  className="mx-auto h-12 w-12 text-gray-400"
                  stroke="currentColor"
                  fill="none"
                  viewBox="0 0 48 48"
                >
                  <path
                    d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <div className="mt-4">
                  <label
                    htmlFor="file-upload"
                    className="cursor-pointer text-primary-600 hover:text-primary-700 font-medium"
                  >
                    클릭하여 파일 선택
                  </label>
                  <span className="text-gray-500"> 또는 드래그 앤 드롭</span>
                </div>
                <p className="mt-2 text-sm text-gray-500">
                  PNG, JPG, GIF 파일을 업로드하세요
                </p>
                <input
                  ref={fileInputRef}
                  id="file-upload"
                  name="file-upload"
                  type="file"
                  className="sr-only"
                  accept="image/*"
                  onChange={handleFileInputChange}
                />
              </div>
            )}
          </div>

          {/* 문맥 텍스트 입력 */}
          <div>
            <label
              htmlFor="context-text"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              문맥 텍스트
            </label>
            <textarea
              id="context-text"
              value={contextText}
              onChange={(e) => setContextText(e.target.value)}
              rows={6}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-all resize-none"
              placeholder="이미지와 관련된 문맥 정보를 입력해주세요. 예: '웹사이트 메인 페이지의 히어로 이미지', '블로그 포스트의 썸네일' 등"
            />
          </div>

          {/* 업로드 버튼 */}
          <button
            type="submit"
            disabled={isUploading || !file || !contextText.trim()}
            className="w-full py-3 px-6 bg-primary-600 text-white font-semibold rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105 active:scale-95"
          >
            {isUploading ? (
              <span className="flex items-center justify-center">
                <svg
                  className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                업로드 중...
              </span>
            ) : (
              '업로드 및 분석 시작'
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default UploadForm;

