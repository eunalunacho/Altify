import { useEffect, useRef, useState, useCallback } from 'react';
import client from '../api/client';

const ReviewPanel = ({ task, imageUrl, onApprovalSuccess }) => {
  const [selectedAlt, setSelectedAlt] = useState(null);
  const [editedAlt, setEditedAlt] = useState('');
  const [originalTexts, setOriginalTexts] = useState({}); // 각 후보의 원본 텍스트 저장
  const [isSaving, setIsSaving] = useState(false);
  const [altCandidates, setAltCandidates] = useState([]);
  const [isApproved, setIsApproved] = useState(false);
  const [hasUserEdited, setHasUserEdited] = useState(false); // 사용자가 수정했는지 추적
  const textareaRef = useRef(null);
  const selectionRef = useRef(null); // 현재 선택된 후보 ID 추적
  const isEditingRef = useRef(false); // 현재 편집 중인지 추적 (포커스 유지용)

  // 초기화: task가 변경될 때만 실행
  useEffect(() => {
    if (task && task.alt_generated_1) {
      // 백엔드에서 받은 2개의 ALT 후보
      const alt1 = task.alt_generated_1;
      const alt2 = task.alt_generated_2 || alt1; // ALT2가 없으면 ALT1 사용
      
      const candidates = [
        { id: 1, text: alt1, isOriginal: true },
        { id: 2, text: alt2, isOriginal: false }
      ];
      
      setAltCandidates(candidates);
      
      // 원본 텍스트 저장
      setOriginalTexts({
        1: alt1,
        2: alt2
      });
      
      // task가 변경되면 항상 초기화 (기본값으로 첫 번째 선택)
      // 단, 이미 승인된 task가 아닌 경우에만 초기화
      const wasApproved = task.is_approved === true;
      setSelectedAlt(1);
      setEditedAlt(alt1);
      setHasUserEdited(false);
      setIsApproved(wasApproved); // task의 승인 상태 반영
      selectionRef.current = 1;
    }
  }, [task]); // task만 의존성으로 설정

  const handleAltSelect = useCallback((candidateId, preserveEdit = false) => {
    if (isApproved) return;

    // 같은 후보를 다시 클릭해도 선택 유지 (선택 해제하지 않음)
    if (selectedAlt === candidateId && !preserveEdit) {
      return;
    }
    
    setSelectedAlt(candidateId);
    selectionRef.current = candidateId;
    
    // preserveEdit가 true이거나 사용자가 수정한 내용이 있으면 editedAlt 유지
    // 그렇지 않으면 선택한 후보의 원본 텍스트로 설정
    if (!preserveEdit && !hasUserEdited) {
      const candidate = altCandidates.find((c) => c.id === candidateId);
      if (candidate) {
        setEditedAlt(candidate.text);
      }
    }
    // preserveEdit가 true이거나 hasUserEdited가 true면 editedAlt는 그대로 유지
  }, [isApproved, selectedAlt, hasUserEdited, altCandidates]);

  // editedAlt 변경 핸들러: 사용자가 수정했는지 추적
  const handleEditedAltChange = useCallback((e) => {
    const newValue = e.target.value;
    setEditedAlt(newValue);
    
    // 원본 텍스트와 다르면 사용자가 수정한 것으로 간주
    const currentOriginal = originalTexts[selectionRef.current || 1];
    if (newValue !== currentOriginal) {
      setHasUserEdited(true);
    } else {
      // 원본과 같아지면 수정 취소로 간주
      setHasUserEdited(false);
    }
  }, [originalTexts]);

  // 텍스트 영역 클릭 핸들러: 포커스 유지 및 편집 상태 보존
  const handleTextareaClick = useCallback((e) => {
    e.stopPropagation(); // 이벤트 버블링 방지로 다른 곳 클릭 시 상태 변경 방지
  }, []);

  // 텍스트 영역 포커스 핸들러: 편집 상태 보존
  const handleTextareaFocus = useCallback(() => {
    isEditingRef.current = true; // 편집 중 플래그 설정
  }, []);

  // 텍스트 영역 블러 핸들러: 편집 상태 보존
  const handleTextareaBlur = useCallback(() => {
    // 약간의 지연 후 플래그 해제 (다른 이벤트 처리 후)
    setTimeout(() => {
      isEditingRef.current = false;
    }, 100);
  }, []);


  const handleApproval = async () => {
    // editedAlt가 비어있으면 기본값(1번 후보) 사용
    let finalAltText = editedAlt.trim();
    let finalSelectedIndex = selectedAlt;
    
    // 사용자가 아무것도 선택하지 않았거나 editedAlt가 비어있으면
    // 기본값으로 1번 후보 사용
    if (!finalAltText || selectedAlt === null || selectedAlt === undefined) {
      finalAltText = originalTexts[1] || altCandidates[0]?.text || '';
      finalSelectedIndex = 1;
      setSelectedAlt(1);
      setEditedAlt(finalAltText);
    }
    
    // 여전히 비어있으면 에러
    if (!finalAltText) {
      alert('ALT 텍스트를 입력해주세요.');
      return;
    }

    // finalSelectedIndex가 유효하지 않으면 기본값으로 1 설정
    if (!finalSelectedIndex || (finalSelectedIndex !== 1 && finalSelectedIndex !== 2)) {
      finalSelectedIndex = 1;
    }

    setIsSaving(true);

    try {
      // 백엔드에 최종 승인 ALT 저장 API 호출
      // selected_alt_index도 함께 전송 (1 또는 2)
      const response = await client.patch(`/tasks/${task.id}/approve`, {
        final_alt: finalAltText,
        is_approved: true,
        selected_alt_index: finalSelectedIndex || 1
      });

      if (response.data) {
        alert('ALT 텍스트가 성공적으로 저장되었습니다!');
        setIsApproved(true);
        setAltCandidates([
          { id: 'final', text: finalAltText, isOriginal: true }
        ]);
        setSelectedAlt('final');
        if (onApprovalSuccess) {
          onApprovalSuccess(response.data);
        }
      }
    } catch (error) {
      console.error('승인 저장 오류:', error);
      alert('저장 중 오류가 발생했습니다. 다시 시도해주세요.');
      // 에러는 client.js의 인터셉터에서 처리됨
    } finally {
      setIsSaving(false);
    }
  };

  if (!task || !imageUrl) {
    return null;
  }

  const renderCandidateCard = (candidate) => {
    const isSelected = selectedAlt === candidate.id;

    return (
      <div
        key={candidate.id}
        className={`border-2 rounded-lg p-4 transition-all ${
          isSelected
            ? 'border-primary-500 bg-primary-50'
            : 'border-gray-200 hover:border-primary-300'
        } cursor-pointer`}
        onClick={(e) => {
          // 텍스트 영역이 포커스되어 있거나 편집 중이면 후보 선택 시에도 편집 내용 보존
          const isTextareaFocused = document.activeElement === textareaRef.current || isEditingRef.current;
          handleAltSelect(candidate.id, isTextareaFocused);
        }}
      >
        <div className="flex items-start space-x-3">
          <input
            type="radio"
            name="alt-candidate"
            checked={isSelected}
            onChange={() => handleAltSelect(candidate.id)}
            className="mt-1"
            onClick={(e) => e.stopPropagation()} // 이벤트 버블링 방지
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
    );
  };

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
              {altCandidates.map((candidate) => renderCandidateCard(candidate))}  
            </div>

            {/* 선택된 ALT 편집 영역 */}
            <div className="mt-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                최종 ALT 텍스트 (수정 가능)
              </label>
              <textarea
                ref={textareaRef}
                value={editedAlt}
                onChange={handleEditedAltChange}
                onClick={handleTextareaClick}
                onFocus={handleTextareaFocus}
                onBlur={handleTextareaBlur}
                readOnly={isApproved}
                rows={6}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none transition-all resize-none"
                placeholder="ALT 텍스트를 입력하거나 수정해주세요..."
              />
              <div className="mt-2 flex items-center justify-between">
                <p className="text-xs text-gray-500">
                  {isApproved
                    ? '최종으로 발행된 ALT 텍스트입니다.'
                    : '선택한 후보를 기반으로 자유롭게 수정할 수 있습니다.'}
                </p>
                {hasUserEdited && !isApproved && (
                  <button
                    type="button"
                    onClick={() => {
                      const currentOriginal = originalTexts[selectionRef.current || 1];
                      setEditedAlt(currentOriginal);
                      setHasUserEdited(false);
                    }}
                    className="text-xs text-primary-600 hover:text-primary-700 underline"
                  >
                    원본으로 복원
                  </button>
                )}
              </div>
            </div>

            {/* 승인 버튼 - editedAlt가 있으면 활성화 */}
            <button
              onClick={handleApproval}
              disabled={isSaving || isApproved || !editedAlt.trim()}
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

