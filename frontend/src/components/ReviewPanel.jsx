import { useState, useEffect } from 'react';
import client from '../api/client';

const ReviewPanel = ({ task, imageUrl, onApprovalSuccess }) => {
  const [selectedAlt, setSelectedAlt] = useState(null);
  const [editedAlt, setEditedAlt] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [altCandidates, setAltCandidates] = useState([]);

  useEffect(() => {
    if (task && task.alt_generated_1) {
      // 백엔드에서 받은 2개의 ALT 후보
      const alt1 = task.alt_generated_1;
      const alt2 = task.alt_generated_2 || alt1; // ALT2가 없으면 ALT1 사용
      
      setAltCandidates([
        { id: 1, text: alt1, isOriginal: true },
        { id: 2, text: alt2, isOriginal: false }
      ]);
      
      // 기본값으로 첫 번째 선택
      setSelectedAlt(1);
      setEditedAlt(alt1);
    }
  }, [task]);

  const handleAltSelect = (candidateId) => {
    setSelectedAlt(candidateId);
    const candidate = altCandidates.find(c => c.id === candidateId);
    if (candidate) {
      setEditedAlt(candidate.text);
    }
  };

  const handleApproval = async () => {
    if (!editedAlt.trim()) {
      alert('ALT 텍스트를 입력해주세요.');
      return;
    }

    setIsSaving(true);

    try {
      // 백엔드에 최종 승인 ALT 저장 API 호출
      // 실제 API 엔드포인트는 백엔드에 맞게 수정 필요
      const response = await client.patch(`/tasks/${task.id}/approve`, {
        final_alt: editedAlt.trim(),
        is_approved: true
      });

      if (response.data) {
        alert('ALT 텍스트가 성공적으로 저장되었습니다!');
        if (onApprovalSuccess) {
          onApprovalSuccess(response.data);
        }
      }
    } catch (error) {
      console.error('승인 저장 오류:', error);
      // 에러는 client.js의 인터셉터에서 처리됨
    } finally {
      setIsSaving(false);
    }
  };

  if (!task || !imageUrl) {
    return null;
  }

  return (
    <div className="w-full max-w-6xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-2xl font-bold text-gray-800">ALT 텍스트 검토 및 승인</h2>
          <p className="text-gray-600 mt-2">AI가 생성한 ALT 텍스트를 검토하고 최종 승인해주세요.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
          {/* 좌측: 원본 이미지 */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-700">원본 이미지</h3>
            <div className="border-2 border-gray-200 rounded-lg overflow-hidden">
              <img
                src={imageUrl}
                alt="업로드된 이미지"
                className="w-full h-auto object-contain max-h-96 mx-auto"
              />
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-sm text-gray-600">
                <span className="font-medium">문맥:</span> {task.context_text}
              </p>
            </div>
          </div>

          {/* 우측: ALT 후보 선택 및 편집 */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-gray-700">ALT 텍스트 후보</h3>
            
            {/* ALT 후보 카드들 */}
            <div className="space-y-3">
              {altCandidates.map((candidate) => (
                <div
                  key={candidate.id}
                  className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
                    selectedAlt === candidate.id
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-primary-300'
                  }`}
                  onClick={() => handleAltSelect(candidate.id)}
                >
                  <div className="flex items-start space-x-3">
                    <input
                      type="radio"
                      name="alt-candidate"
                      checked={selectedAlt === candidate.id}
                      onChange={() => handleAltSelect(candidate.id)}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <span className="text-sm font-medium text-gray-700">
                          후보 {candidate.id}
                        </span>
                        {candidate.isOriginal && (
                          <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                            추천
                          </span>
                        )}
                      </div>
                      <p className="text-gray-700 text-sm leading-relaxed">
                        {candidate.text}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 선택된 ALT 편집 영역 */}
            <div className="mt-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                최종 ALT 텍스트 (수정 가능)
              </label>
              <textarea
                value={editedAlt}
                onChange={(e) => setEditedAlt(e.target.value)}
                rows={6}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-all resize-none"
                placeholder="ALT 텍스트를 입력하거나 수정해주세요..."
              />
              <p className="mt-2 text-xs text-gray-500">
                선택한 후보를 기반으로 자유롭게 수정할 수 있습니다.
              </p>
            </div>

            {/* 승인 버튼 */}
            <button
              onClick={handleApproval}
              disabled={isSaving || !editedAlt.trim()}
              className="w-full mt-6 py-3 px-6 bg-primary-600 text-white font-semibold rounded-lg hover:bg-primary-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-all transform hover:scale-105 active:scale-95"
            >
              {isSaving ? (
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
                  저장 중...
                </span>
              ) : (
                '최종 승인 및 저장'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReviewPanel;

