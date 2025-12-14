import { useState, useRef } from 'react';
import client from '../api/client';

const UploadForm = ({ onUploadSuccess }) => {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
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

  const handleAttachClick = () => {
      if (fileInputRef.current) {
        fileInputRef.current.click();
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
      formData.append('문맥텍스트', title ? `${title}\n\n${contextText}` : contextText);

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
    <div className="w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
        <form onSubmit={handleSubmit} className="flex flex-col h-full">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between px-6 py-5 border-b border-gray-200 bg-gray-50">
            <div>
              <p className="text-sm font-semibold text-primary-600">블로그 글쓰기</p>
              <h2 className="text-2xl font-bold text-gray-900">새 포스트 작성</h2>
              <p className="text-sm text-gray-500 mt-1">
                이미지와 문맥을 첨부해 발행을 누르면 업로드 및 분석이 시작됩니다.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleAttachClick}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
              >
                이미지 첨부
              </button>
              <button
                type="submit"
                disabled={isUploading || !file || !contextText.trim()}
                className="px-5 py-2.5 bg-primary-600 text-white font-semibold rounded-lg shadow hover:bg-primary-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                {isUploading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg
                      className="animate-spin h-4 w-4 text-white"
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
                    발행 중...
                  </span>
                ) : (
                  '발행'
                )}
              </button>
            </div>
          </div>

          <div className="p-6 space-y-6">
            <div>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="제목을 입력하세요"
                className="w-full text-2xl font-bold text-gray-900 border-none focus:ring-0 placeholder:text-gray-400"
              />
            </div>

            <div className="border border-gray-200 rounded-xl overflow-hidden">
              <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-200 text-gray-500">
                <button type="button" className="p-2 hover:text-primary-600" title="굵게">
                  <span className="font-bold">B</span>
                </button>
                <button type="button" className="p-2 hover:text-primary-600 italic" title="기울임">
                  I
                </button>
                <button type="button" className="p-2 hover:text-primary-600" title="밑줄">
                  <span className="underline">U</span>
                </button>
                <span className="h-6 w-px bg-gray-200" aria-hidden="true"></span>
                <button type="button" className="p-2 hover:text-primary-600" title="목록">
                  • • •
                </button>
                <button type="button" className="p-2 hover:text-primary-600" title="인용">
                  ❝
                </button>
                <span className="h-6 w-px bg-gray-200" aria-hidden="true"></span>
                <button
                  type="button"
                  onClick={handleAttachClick}
                  className="ml-auto px-3 py-1.5 bg-white border border-gray-300 rounded-lg hover:bg-gray-100 text-sm font-medium"
                  >
                  이미지 추가
                </button>
              </div>

              <div className="p-4 space-y-4" onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
                {preview ? (
                  <div className="space-y-3">
                    <img
                      src={preview}
                      alt="미리보기"
                      className="w-full max-h-[520px] object-contain rounded-xl bg-gray-100 shadow-sm"
                    />
                    <div className="flex items-center justify-between text-sm text-gray-500">
                      <span className="truncate">{file?.name}</span>
                      <button
                        type="button"
                        onClick={handleRemoveFile}
                        className="text-red-500 hover:text-red-600 font-medium"
                      >
                        이미지 제거
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-10 text-center transition-colors ${
                      isDragging ? 'border-primary-400 bg-primary-50/60' : 'border-gray-200 bg-white'
                    }`} 
                  >
                    클릭하여 파일 선택
                    <svg
                      className="h-12 w-12 text-gray-400"
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
                    <div className="flex flex-col gap-1 text-gray-600">
                      <p className="font-medium">이미지를 드래그 앤 드롭하거나 추가 버튼을 눌러 첨부하세요.</p>
                      <p className="text-sm text-gray-500">PNG, JPG, GIF 파일을 지원합니다.</p>
                    </div>
                    <button
                      type="button"
                      onClick={handleAttachClick}
                      className="px-4 py-2 bg-primary-50 text-primary-700 border border-primary-100 rounded-lg hover:bg-primary-100"
                    >
                      이미지 불러오기
                    </button>
                  </div>
                )}

                <div>
                  <textarea
                    id="context-text"
                    value={contextText}
                    onChange={(e) => setContextText(e.target.value)}
                    rows={12}
                    className="w-full px-1 py-2 text-base leading-7 text-gray-800 placeholder:text-gray-400 border-0 focus:ring-0 resize-none"
                    placeholder="블로그 글을 작성하듯 이미지에 대한 문맥을 자유롭게 입력하세요. 위치, 분위기, 등장인물, 필요한 안내 문구 등을 자세히 적어주시면 더 정확한 ALT 텍스트를 생성할 수 있습니다."
                  /> 
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between text-sm text-gray-500">
              <p>이미지와 문맥을 모두 입력하면 상단의 발행 버튼이 활성화됩니다.</p>
              <p className="font-medium text-primary-600">자동 저장은 지원하지 않으니 발행을 눌러주세요.</p>
            </div>
          </div>

          <input
            ref={fileInputRef}
            id="file-upload"
            name="file-upload"
            type="file"
            className="sr-only"
            accept="image/*"
            onChange={handleFileInputChange}
          />
        </form>
      </div>
    </div>
  );
};

export default UploadForm;
