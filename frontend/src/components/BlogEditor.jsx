import { useState, useRef, useEffect, useCallback } from 'react';
import client from '../api/client';

// 블록 타입 정의
const EDITOR_STAGE = {
  EDITING: 'editing',
  GENERATING: 'generating',
  FINALIZED: 'finalized'
};

const BlogEditor = ({ onPublishSuccess }) => {
  const [stage, setStage] = useState(EDITOR_STAGE.EDITING);
  const [imageTasks, setImageTasks] = useState(new Map()); // imageId -> task 정보
  const [isPublishing, setIsPublishing] = useState(false);
  const [, setEditorChangeCount] = useState(0); // 에디터 변경 감지
  const [prePublishHTML, setPrePublishHTML] = useState('');
  const [selectedAlts, setSelectedAlts] = useState(new Map()); // imageId -> {choice, text}
  const editorRef = useRef(null);
  const fileInputRef = useRef(null);
  const imageIdCounter = useRef(1);
  const imageSequenceCounter = useRef(0); // 이미지 삽입 순서 추적
  const imageInsertQueue = useRef([]); // 이미지 삽입 큐
  const isProcessingQueue = useRef(false); // 큐 처리 중 플래그
  const imageIdToTaskIdRef = useRef(new Map()); // imageId -> taskId 매핑
  const imageDataMapRef = useRef(new Map()); // imageId -> {file, preview} 매핑
  const imageTasksRef = useRef(new Map()); // imageTasks 상태의 최신 값을 ref로도 관리
  const selectedAltsRef = useRef(new Map());
  const editingElementsRef = useRef(new Map()); // imageId -> {element, choice} 편집 중인 요소 추적
  const lastUpdateTimeRef = useRef(0); // 마지막 tooltip 업데이트 시간 추적 (중복 호출 방지)

  const isEditorLocked = stage !== EDITOR_STAGE.EDITING;
  const isFinalized = stage === EDITOR_STAGE.FINALIZED;

  // imageTasks 상태와 ref를 동기화
  useEffect(() => {
    imageTasksRef.current = imageTasks;
  }, [imageTasks]);

  // 선택한 ALT 상태 동기화
  useEffect(() => {
    selectedAltsRef.current = selectedAlts;
  }, [selectedAlts]);

  // 이미지 삽입 큐 처리
  const processImageQueue = useCallback(() => {
    if (isProcessingQueue.current || imageInsertQueue.current.length === 0) {
      return;
    }

    isProcessingQueue.current = true;
    const queueItem = imageInsertQueue.current.shift();
    
    const { file, imageId, sequence, savedRange } = queueItem;
    const reader = new FileReader();
    
    reader.onloadend = () => {
      const preview = reader.result;
      const editor = editorRef.current;
      
      if (!editor) {
        isProcessingQueue.current = false;
        processImageQueue(); // 다음 항목 처리
        return;
      }

      // 이미지 데이터 저장
      imageDataMapRef.current.set(imageId, { file, preview, sequence });

      editor.focus();

      // 저장된 범위 복원
      const selection = window.getSelection();
      selection.removeAllRanges();
      
      let insertRange = savedRange;
      
      // 범위가 유효한지 확인
      try {
        const testRange = savedRange.cloneRange();
        selection.addRange(testRange);
        insertRange = testRange;
      } catch (e) {
        // 범위가 유효하지 않으면 에디터 끝에 설정
        const newRange = document.createRange();
        newRange.selectNodeContents(editor);
        newRange.collapse(false);
        selection.addRange(newRange);
        insertRange = newRange;
      }

      // 이미지 요소 생성
      const img = document.createElement('img');
      img.src = preview;
      img.setAttribute('data-image-id', imageId);
      img.setAttribute('data-sequence', sequence);
      img.className = 'max-w-full h-auto rounded-lg my-4 mx-auto max-h-96 cursor-pointer';
      img.style.display = 'block';
      img.contentEditable = false;

      if (!isEditorLocked) {
        img.addEventListener('click', (e) => {
          if (e.ctrlKey || e.metaKey) {
            const targetImageId = img.getAttribute('data-image-id');
            img.remove();
            imageDataMapRef.current.delete(targetImageId);
          }
        });
      }

      // 이미지 삽입
      insertRange.insertNode(img);
      
      const br = document.createElement('br');
      insertRange.setStartAfter(img);
      insertRange.insertNode(br);
      
      insertRange.setStartAfter(br);
      insertRange.collapse(true);
      selection.removeAllRanges();
      selection.addRange(insertRange);
      
      editor.focus();

      // 다음 항목 처리
      isProcessingQueue.current = false;
      setEditorChangeCount(prev => prev + 1);
      processImageQueue();
    };
    
    reader.readAsDataURL(file);
  }, [isEditorLocked]);

  // 이미지를 에디터에 삽입 (큐에 추가)
  const insertImageToEditor = (file, imageId) => {
    if (!editorRef.current) return;

    const editor = editorRef.current;
    const sequence = imageSequenceCounter.current++;
    
    // 현재 커서 위치를 즉시 저장
    let savedRange = null;
    const selection = window.getSelection();
    
    if (selection.rangeCount > 0) {
      const currentRange = selection.getRangeAt(0);
      const container = currentRange.commonAncestorContainer;
      
      const isInEditor = editor.contains(
        container.nodeType === Node.TEXT_NODE ? container.parentNode : container
      );
      
      if (isInEditor) {
        savedRange = currentRange.cloneRange();
      }
    }
    
    if (!savedRange) {
      savedRange = document.createRange();
      savedRange.selectNodeContents(editor);
      savedRange.collapse(false);
    }
    
    // 큐에 추가
    imageInsertQueue.current.push({
      file,
      imageId,
      sequence,
      savedRange
    });
    
    // 큐 처리 시작
    processImageQueue();
  };

  // 파일 선택 핸들러
  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file && file.type.startsWith('image/')) {
      const imageId = `img-${imageIdCounter.current++}`;
      insertImageToEditor(file, imageId);
    }
    // input 초기화
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // 에디터 입력 이벤트 감지 (텍스트 변경 시 리렌더링 유도)
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return undefined;

    const handleEditorInput = () => {
      if (isEditorLocked) return;
      setEditorChangeCount(prev => prev + 1);
    };

    editor.addEventListener('input', handleEditorInput);
    editor.addEventListener('drop', handleEditorInput);

    return () => {
      editor.removeEventListener('input', handleEditorInput);
      editor.removeEventListener('drop', handleEditorInput);
    };
  }, [isEditorLocked]);

  // 드래그 앤 드롭
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isEditorLocked) return;

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
      const imageId = `img-${imageIdCounter.current++}`;
      insertImageToEditor(file, imageId);
    }
  };

  // 텍스트 업데이트
  const handleTextChange = (blockId, content) => {
    if (isEditorLocked) return;

    // 이 함수는 텍스트 블록에 대한 것이므로, 이미지 블록에는 적용되지 않음
    // 이미지 블록의 content는 이미지 데이터를 포함하므로, 텍스트 업데이트는 필요 없음
  };

  // 블록 삭제
  const handleDeleteBlock = (blockId) => {
    if (isEditorLocked) return;

    // 이 함수는 텍스트 블록에 대한 것이므로, 이미지 블록에는 적용되지 않음
    // 이미지 블록은 클릭으로 삭제되므로, 여기서는 처리하지 않음
  };

  // 이미지-문맥 쌍 추출 (HTML 파싱) - 완성된 쌍만 추출
  const extractImageContextPairs = () => {
    if (!editorRef.current) return [];

    const editor = editorRef.current;
    
    // 실제 에디터 DOM에서 직접 이미지 찾기
    const images = Array.from(editor.querySelectorAll('img[data-image-id]'))
      .map(img => ({
        element: img,
        imageId: img.getAttribute('data-image-id'),
        sequence: parseInt(img.getAttribute('data-sequence') || '999999', 10)
      }))
      .sort((a, b) => a.sequence - b.sequence);

    if (images.length === 0) return [];

    const pairs = [];

    // 모든 이미지 처리 (첫 이미지부터)
    for (let i = 0; i < images.length; i++) {
      const imageInfo = images[i];
      const img = imageInfo.element;
      const imageId = imageInfo.imageId;
      const imageData = imageDataMapRef.current.get(imageId);

      if (!imageData) continue;

      // 이미지 다음의 텍스트를 추출하는 함수
      const getTextAfterImage = (imageElement) => {
        const textParts = [];
        let node = imageElement;

        // 이미지 다음 노드들을 순회
        while (node) {
          // 다음 형제 노드로 이동
          node = node.nextSibling;

          if (!node) {
            // 형제가 없으면 부모의 다음 형제 확인
            const parent = imageElement.parentNode;
            if (parent && parent !== editor) {
              node = parent.nextSibling;
              imageElement = parent; // 다음 반복에서 parent의 형제를 확인
            } else {
              break;
            }
          }

          if (!node) break;

          // 다음 이미지를 만나면 중단
          if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.tagName === 'IMG' && node.getAttribute('data-image-id')) {
              break;
            }
            // 요소 내부에 다음 이미지가 있는지 확인
            const nextImage = node.querySelector && node.querySelector('img[data-image-id]');
            if (nextImage) {
              break;
            }
          }

          // 텍스트 추출
          if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent.trim();
            if (text) {
              textParts.push(text);
            }
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            // <br> 태그는 건너뛰기
            if (node.tagName === 'BR') {
              continue;
            }
            // 이미지가 아닌 요소의 텍스트 추출
            if (node.tagName !== 'IMG') {
              const text = node.textContent.trim();
              if (text) {
                textParts.push(text);
              }
            }
          }

          // 너무 많은 텍스트를 수집하지 않도록 제한
          if (textParts.join(' ').length > 500) break;
        }

        return textParts.join(' ').trim();
      };

      const contextText = getTextAfterImage(img);

      // 텍스트가 있는 경우만 쌍으로 추가 (완성된 쌍만)
      if (contextText) {
        pairs.push({
          imageId: imageId,
          imageBlock: {
            id: imageId,
            file: imageData.file,
            preview: imageData.preview
          },
          contextText: contextText
        });
      }
    }

    return pairs;
  };

  const clearAltDecorations = useCallback(() => {
    if (!editorRef.current) return;
    const decorations = editorRef.current.querySelectorAll('.alt-tooltip, .alt-loading-overlay');
    decorations.forEach((node) => node.remove());
  }, []);

  const handleAltSelection = useCallback((imageId, choice, text) => {
    setSelectedAlts(prev => {
      const updated = new Map(prev);
      updated.set(imageId, { choice, text: text || '' });
      return updated;
    });
  }, []);

  const handleAltEdit = useCallback((imageId, text) => {
    setSelectedAlts(prev => {
      const updated = new Map(prev);
      const current = updated.get(imageId) || { choice: null, text: '' };
      updated.set(imageId, { ...current, text });
      return updated;
    });
  }, []);

  // ALT 후보 말풍선 및 로딩 아이콘 업데이트 (imageTasks를 파라미터로 받음)
  const updateAltTooltips = useCallback((currentImageTasks) => {
    if (!editorRef.current) return;

    const editor = editorRef.current;
    
    // 편집 중인 요소의 내용 저장 (tooltip 제거 전에)
    const editingInfo = new Map(); // imageId -> {text, choice}
    const images = editor.querySelectorAll('img[data-image-id]');
    
    images.forEach((img) => {
      const imageId = img.getAttribute('data-image-id');
      const editingData = editingElementsRef.current.get(imageId);
      if (editingData && editingData.element && document.contains(editingData.element)) {
        // 편집 중인 요소가 있고 아직 DOM에 있으면 내용 저장
        const currentText = editingData.element.textContent || '';
        editingInfo.set(imageId, {
          text: currentText,
          choice: editingData.choice
        });
      }
    });

    // 모든 tooltip 제거 (이전 코드 방식)
    clearAltDecorations();

    // 모든 이미지에 대해 tooltip 생성
    images.forEach((img) => {
      const imageId = img.getAttribute('data-image-id');
      const task = currentImageTasks.get(imageId);

      if (!task) {
        return;
      }

      const parent = img.parentElement;
      if (parent) {
        parent.style.position = 'relative';
      }

      // 말풍선 생성
      if (task.status === 'PROCESSING' || task.status === 'PENDING') {
        const overlay = document.createElement('div');
        overlay.className = 'alt-loading-overlay absolute inset-0 flex items-start justify-end pointer-events-none';
        overlay.innerHTML = `
          <div class="bg-white/80 rounded-full p-2 m-2 shadow-sm border border-yellow-200">
            <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-yellow-600"></div>
          </div>
        `;
        // 이미지 다음에 말풍선 삽입
        if (parent) {
          parent.appendChild(overlay);
        }
        return;
      }

      if (task.status === 'FAILED') {
        const tooltip = document.createElement('div');
        tooltip.className = 'alt-tooltip bg-red-50 border border-red-200 rounded-lg p-3 text-center text-sm text-red-800 mt-2';
        tooltip.textContent = 'ALT 텍스트 생성 실패';
        if (parent) {
          parent.insertBefore(tooltip, img.nextSibling);
        }
        return;
      }

      if (task.status === 'DONE' && (task.alt1 || task.alt2)) {
        const selectedInfo = selectedAltsRef.current.get(imageId);
        const savedEditingInfo = editingInfo.get(imageId);
        
        const tooltip = document.createElement('div');
        tooltip.className = 'alt-tooltip bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3 mt-2';

        const title = document.createElement('div');
        title.className = 'text-sm font-semibold text-blue-800';
        title.textContent = '생성된 ALT 텍스트 후보';
        tooltip.appendChild(title);

        const candidates = document.createElement('div');
        candidates.className = 'space-y-2';

        const createCandidate = (index, text) => {
          const isSelected = selectedInfo?.choice === index;
          const candidate = document.createElement('div');
          candidate.className = `flex items-start gap-2 p-3 border rounded-lg cursor-pointer transition ${isSelected ? 'border-primary-500 bg-white shadow-sm' : 'border-gray-200 hover:border-primary-300'}`;

          const icon = document.createElement('div');
          icon.className = 'text-lg';
          icon.textContent = index === 1 ? '💬1' : '💬2';
          candidate.appendChild(icon);

          const content = document.createElement('div');
          content.className = 'flex-1 text-gray-800 whitespace-pre-wrap';
          
          // 편집 중이었던 내용이 있으면 그것을 사용, 없으면 선택된 텍스트 사용
          let chosenText = text || '';
          if (isSelected) {
            if (savedEditingInfo && savedEditingInfo.choice === index) {
              chosenText = savedEditingInfo.text;
            } else if (selectedInfo?.text) {
              chosenText = selectedInfo.text;
            }
          }
          content.textContent = chosenText;

          if (isSelected && !isFinalized) {
            content.contentEditable = true;
            content.className += ' outline-none focus:ring-2 focus:ring-primary-500 rounded';
            
            // 편집 중인 요소 추적
            editingElementsRef.current.set(imageId, {
              element: content,
              choice: index
            });
            
            // blur 이벤트: 다른 곳 클릭 시에도 내용 저장
            content.addEventListener('blur', (e) => {
              const currentText = e.currentTarget.textContent || '';
              handleAltEdit(imageId, currentText);
            });
            
            content.addEventListener('input', (e) => {
              const currentText = e.currentTarget.textContent || '';
              handleAltEdit(imageId, currentText);
            });
            
            content.addEventListener('click', (e) => e.stopPropagation());
            
            // focus 이벤트: 포커스 시 편집 중인 요소로 표시
            content.addEventListener('focus', () => {
              editingElementsRef.current.set(imageId, {
                element: content,
                choice: index
              });
            });
          }

          candidate.addEventListener('click', (e) => {
            // contentEditable 요소를 클릭한 경우는 무시
            if (e.target === content && content.contentEditable === 'true') {
              return;
            }
            handleAltSelection(imageId, index, text || '');
          });

          candidate.appendChild(content);
          return candidate;
        };

        if (task.alt1) {
          candidates.appendChild(createCandidate(1, task.alt1));
        }
        if (task.alt2) {
          candidates.appendChild(createCandidate(2, task.alt2));
        }

        tooltip.appendChild(candidates);

        if (parent) {
          parent.insertBefore(tooltip, img.nextSibling);
        }
      }
    });
  }, [clearAltDecorations, handleAltEdit, handleAltSelection, isFinalized]);

  // 발행 핸들러
  const startAltGeneration = async () => {
    const pairs = extractImageContextPairs();

    if (pairs.length === 0) {
      alert('최소 하나의 이미지가 필요합니다.');
      return;
    }

    if (editorRef.current) {
      setPrePublishHTML(editorRef.current.innerHTML);
    }

    setIsPublishing(true);

    try {
      // 모든 이미지-문맥 쌍을 백엔드에 전송
      const formData = new FormData();
      
      pairs.forEach((pair) => {
        formData.append(`images`, pair.imageBlock.file);
        formData.append(`contexts`, pair.contextText);
      });

      const response = await client.post('/tasks/bulk-upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      const tasks = Array.isArray(response.data) ? response.data : response.data?.tasks;

      if (tasks && tasks.length > 0) {
        // 각 이미지에 task 정보 매핑
        const newImageTasks = new Map();
        const newImageIdToTaskId = new Map();
        pairs.forEach((pair, index) => {
          if (tasks[index]) {
            const taskId = tasks[index].id;
            newImageTasks.set(pair.imageId, {
              taskId: taskId,
              status: tasks[index].status,
              alt1: null,
              alt2: null
            });
            newImageIdToTaskId.set(pair.imageId, taskId);
          }
        });
        imageIdToTaskIdRef.current = newImageIdToTaskId;
        
        // 상태 업데이트
        setImageTasks(newImageTasks);
        setStage(EDITOR_STAGE.GENERATING);
        setSelectedAlts(new Map());
        
        // 발행 후 에디터 비활성화
        if (editorRef.current) {
          editorRef.current.contentEditable = false;
        }

        // ALT 후보 말풍선 추가 (상태 업데이트 후 실행)
        setTimeout(() => {
          updateAltTooltips(newImageTasks);
        }, 0);

        if (onPublishSuccess) {
           onPublishSuccess(tasks);
        }
      }
    } catch (error) {
      console.error('발행 오류:', error);
    } finally {
      setIsPublishing(false);
    }
  };

  const finalizeAltSelection = async () => {
    const imageIdToTaskId = imageIdToTaskIdRef.current;
    const pendingSelection = Array.from(imageIdToTaskId.keys()).filter((imageId) => {
      const selection = selectedAltsRef.current.get(imageId);
      const task = imageTasksRef.current.get(imageId);
      return !selection || !selection.choice || !task || task.status !== 'DONE';
    });

    if (pendingSelection.length > 0) {
      alert('모든 이미지에 대해 ALT 후보를 선택한 뒤 발행해주세요.');
      return;
    }

    const payload = Array.from(imageIdToTaskId.entries()).map(([imageId, taskId]) => {
      const selection = selectedAltsRef.current.get(imageId);
      const task = imageTasksRef.current.get(imageId);
      const baseText = selection.choice === 1 ? task?.alt1 : task?.alt2;
      const finalText = (selection.text || baseText || '').trim();
      return {
        task_id: taskId,
        selected_alt_index: selection.choice,
        final_alt: finalText
      };
    });

    setIsPublishing(true);
    try {
      await client.post('/tasks/finalize', payload);
      setStage(EDITOR_STAGE.FINALIZED);

      if (editorRef.current) {
        editorRef.current.contentEditable = false;
        const images = editorRef.current.querySelectorAll('img[data-image-id]');
        images.forEach((img) => {
          const selection = selectedAltsRef.current.get(img.getAttribute('data-image-id'));
          if (selection?.text) {
            img.alt = selection.text;
          }
        });
      }

      setTimeout(() => {
        updateAltTooltips(imageTasksRef.current);
      }, 0);
    } catch (error) {
      console.error('최종 발행 오류:', error);
    } finally {
      setIsPublishing(false);
    }
  };

  // 발행 핸들러
  const handlePublish = async () => {
    if (stage === EDITOR_STAGE.EDITING) {
      await startAltGeneration();
    } else if (stage === EDITOR_STAGE.GENERATING) {
      await finalizeAltSelection();
    }
  };

  // 작업 상태 폴링 (발행 후 자동 시작)
  useEffect(() => {
    if (stage !== EDITOR_STAGE.GENERATING || imageTasks.size === 0) return;

    let pollInterval = null;
    let isPolling = true;

    const pollTasks = async () => {
      if (!isPolling) return;

      try {
        const imageIdToTaskId = imageIdToTaskIdRef.current;
        const taskIds = Array.from(imageIdToTaskId.values());

        if (taskIds.length === 0) return;

        // 모든 task 상태 확인
        const allDone = await Promise.all(
          taskIds.map(async (taskId) => {
            try {
              const response = await client.get(`/tasks/${taskId}`);
              return response.data;
            } catch (error) {
              console.error(`Task ${taskId} 조회 오류:`, error);
              return null;
            }
          })
        );

        // 상태 업데이트 (함수형 업데이트 사용)
        setImageTasks(prevTasks => {
          const updatedImageTasks = new Map(prevTasks);
          let hasUpdates = false;

          allDone.forEach((taskData) => {
            if (!taskData) return;

            // taskId로 imageId 찾기
            let targetImageId = null;
            imageIdToTaskId.forEach((tid, iid) => {
              if (tid === taskData.id) {
                targetImageId = iid;
              }
            });

            if (targetImageId) {
              const currentTask = prevTasks.get(targetImageId);
              
              if (currentTask && (
                currentTask.status !== taskData.status ||
                currentTask.alt1 !== taskData.alt_generated_1 ||
                currentTask.alt2 !== taskData.alt_generated_2
              )) {
                updatedImageTasks.set(targetImageId, {
                  taskId: taskData.id,
                  status: taskData.status,
                  alt1: taskData.alt_generated_1,
                  alt2: taskData.alt_generated_2
                });
                hasUpdates = true;
              }
            }
          });

          // 업데이트가 있으면 말풍선도 업데이트
          // 단, 이미 말풍선이 표시된 경우 중복 생성 방지
          if (hasUpdates) {
            // 상태 업데이트 후 DOM 업데이트를 위해 setTimeout 사용
            // 중복 호출 방지를 위해 짧은 지연 추가
            setTimeout(() => {
              const now = Date.now();
              if (now - lastUpdateTimeRef.current >= 500) {
                lastUpdateTimeRef.current = now;
                updateAltTooltips(updatedImageTasks);
              }
            }, 100);
          }

          return hasUpdates ? updatedImageTasks : prevTasks;
        });

        // 모든 작업이 완료되면 폴링 중지
        const allCompleted = allDone.every(
          task => task && (task.status === 'DONE' || task.status === 'FAILED')
        );

        if (allCompleted) {
          isPolling = false;
          if (pollInterval) {
            clearInterval(pollInterval);
          }
        }
      } catch (error) {
        console.error('상태 폴링 오류:', error);
      }
    };

    pollTasks();
    pollInterval = setInterval(pollTasks, 3000);

    return () => {
      isPolling = false;
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [imageTasks.size, stage, updateAltTooltips]);

  // imageTasks/선택 변경 시 말풍선 업데이트 (추가 안전장치)
  // 단, 폴링 중이 아닐 때만 실행 (중복 호출 방지)
  useEffect(() => {
    if (stage !== EDITOR_STAGE.EDITING && imageTasks.size > 0) {
      const now = Date.now();
      // 최근 1초 이내에 업데이트가 있었으면 스킵 (중복 호출 방지)
      if (now - lastUpdateTimeRef.current < 1000) {
        return;
      }
      lastUpdateTimeRef.current = now;
      updateAltTooltips(imageTasks);
    }
  }, [imageTasks, selectedAlts, stage, updateAltTooltips]);

  const handleResetToDraft = () => {
    if (!editorRef.current) return;

    editorRef.current.innerHTML = prePublishHTML;
    editorRef.current.contentEditable = true;
    setStage(EDITOR_STAGE.EDITING);
    setImageTasks(new Map());
    setSelectedAlts(new Map());
    imageIdToTaskIdRef.current = new Map();
    clearAltDecorations();

    setTimeout(() => {
      const images = editorRef.current.querySelectorAll('img[data-image-id]');
      images.forEach((img) => {
        img.addEventListener('click', (e) => {
          if (e.ctrlKey || e.metaKey) {
            const targetImageId = img.getAttribute('data-image-id');
            img.remove();
            imageDataMapRef.current.delete(targetImageId);
          }
        });
      });
    }, 0);
  };

  const hasImageContextPairs = extractImageContextPairs().length > 0;
  const allTasksCompleted = imageTasks.size > 0 && Array.from(imageTasks.values()).every(task => task.status === 'DONE');
  const allSelectionsMade = allTasksCompleted && Array.from(imageIdToTaskIdRef.current.keys()).every((imageId) => {
    const selection = selectedAltsRef.current.get(imageId);
    const task = imageTasksRef.current.get(imageId);

    if (!selection || !selection.choice) return false;

    const baseText = selection.choice === 1 ? task?.alt1 : task?.alt2;
    return Boolean((selection.text || baseText || '').trim());
  });

  const publishDisabled = isPublishing
    || stage === EDITOR_STAGE.FINALIZED
    || (stage === EDITOR_STAGE.EDITING && !hasImageContextPairs)
    || (stage === EDITOR_STAGE.GENERATING && (!allTasksCompleted || !allSelectionsMade));

  const publishLabel = stage === EDITOR_STAGE.GENERATING
    ? '최종 발행'
    : stage === EDITOR_STAGE.FINALIZED
      ? '발행 완료'
      : '발행';

  return (
    <div className="w-full max-w-4xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-lg">
        {/* 헤더 */}
        <div className="border-b border-gray-200 p-4 flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-800">블로그 글 작성</h2>
          <div className="flex items-center gap-4">
            {/* 이미지 추가 버튼 */}
            {stage === EDITOR_STAGE.EDITING && (
              <label className="cursor-pointer inline-flex items-center px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors">
                <svg
                  className="w-5 h-5 mr-2 text-gray-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                이미지 추가
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </label>
            )}
            {stage === EDITOR_STAGE.GENERATING && (
              <button
                onClick={handleResetToDraft}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg border border-gray-300 hover:bg-gray-200 transition-colors"
                disabled={isPublishing}
              >
                수정
              </button>
            )}
            <button
              onClick={handlePublish}
              disabled={publishDisabled}
              className="px-6 py-2 bg-green-600 text-white font-semibold rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {isPublishing ? '처리 중...' : publishLabel}
            </button>
          </div>
        </div>

        {/* 통합 에디터 영역 */}
        <div className="p-6">
          <div
            ref={editorRef}
            contentEditable={stage === EDITOR_STAGE.EDITING}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            className="min-h-[600px] p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none prose max-w-none"
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}
            suppressContentEditableWarning={true}
            data-placeholder="글을 작성하세요..."
          />
          {stage === EDITOR_STAGE.EDITING && (
            <p className="text-sm text-gray-500 mt-2 px-4">
              💡 이미지를 드래그 앤 드롭하거나 위의 '이미지 추가' 버튼을 사용하세요.
              이미지 삭제: Ctrl/Cmd + 클릭
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default BlogEditor;

