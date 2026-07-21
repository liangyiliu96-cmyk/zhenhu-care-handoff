import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  MenuItem,
  TextField,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { Bot, Check, ChevronDown, ChevronUp, ClipboardPlus, History, Pencil, RotateCcw, Send, Square, X, XCircle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '@/core/api-client';
import {
  decideAssistantActionDraft,
  fetchAssistantActionDrafts,
  fetchAssistantQuickQuestions,
  fetchAssistantSession,
  fetchAssistantSessions,
  generateAssistantActionDrafts,
  resetAssistantSession,
  streamAssistantChat,
  updateAssistantActionDraft,
  type AssistantActionDraft,
  type AssistantCitation,
  type AssistantStreamEvent,
} from '@/services/assistant-service';
import { ASSISTANT_META, type AssistantMode } from '@/core/assistant-modes';

interface PatientAssistantPanelProps {
  patientId?: string;
  title?: string;
  defaultOpen?: boolean;
  assistantMode?: AssistantMode;
  availableModes?: AssistantMode[];
  publicAccess?: boolean;
  onOpenClinicalRecord?: (draft: AssistantActionDraft) => void;
}

interface AssistantMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  citations?: AssistantCitation[];
  completed?: boolean;
  sessionId?: string;
}

type DraftDecision = { draft: AssistantActionDraft; action: 'approve' | 'reject' };

export default function PatientAssistantPanel({
  patientId = '',
  title,
  defaultOpen = false,
  assistantMode: requestedMode,
  availableModes,
  publicAccess = false,
  onOpenClinicalRecord,
}: PatientAssistantPanelProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(defaultOpen);
  const fallbackMode: AssistantMode = sessionStorage.getItem('zhenhu_role') === 'nurse' ? 'nurse' : 'doctor';
  const modes = availableModes?.length ? availableModes : [requestedMode ?? fallbackMode];
  const [assistantMode, setAssistantMode] = useState<AssistantMode>(requestedMode ?? modes[0]);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState('');
  const [showSessions, setShowSessions] = useState(false);
  const [editingDraft, setEditingDraft] = useState<AssistantActionDraft | null>(null);
  const [draftFields, setDraftFields] = useState<Record<string, string>>({});
  const [decision, setDecision] = useState<DraftDecision | null>(null);
  const [decisionComment, setDecisionComment] = useState('');
  const [draftFeedback, setDraftFeedback] = useState('');
  const [draftError, setDraftError] = useState('');
  const streamController = useRef<AbortController>();
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  const modeMeta = ASSISTANT_META[assistantMode];
  const panelTitle = title ?? modeMeta.name;
  const assistantContext = patientId ? 'patient' : 'general';
  const canManageDrafts = Boolean(patientId && !publicAccess && sessionStorage.getItem('zhenhu_role') !== 'nurse');
  const quickQuestions = useQuery({
    queryKey: ['assistant', 'quick-questions', assistantMode, assistantContext, publicAccess],
    queryFn: () => fetchAssistantQuickQuestions(assistantMode, assistantContext, publicAccess),
    enabled: open,
    staleTime: 30_000,
    retry: false,
  });
  const sessions = useQuery({ queryKey: ['assistant', 'sessions'], queryFn: fetchAssistantSessions, enabled: showSessions, staleTime: 10_000 });
  const actionDrafts = useQuery({
    queryKey: ['patient', patientId, 'assistant-action-drafts'],
    queryFn: () => fetchAssistantActionDrafts(patientId),
    enabled: open && canManageDrafts,
    staleTime: 5_000,
    retry: false,
  });

  const refreshClinicalState = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['patient', patientId] }),
      queryClient.invalidateQueries({ queryKey: ['ward'] }),
      queryClient.invalidateQueries({ queryKey: ['patient', patientId, 'assistant-action-drafts'] }),
    ]);
  };

  const reportDraftError = (cause: unknown) => {
    if (cause instanceof ApiClientError && cause.code === 'STATE_VERSION_CONFLICT') {
      setDraftError('患者状态已被更新，已刷新最新数据，请重新核对草稿。');
      void refreshClinicalState();
      return;
    }
    if (cause instanceof ApiClientError && cause.code === 'TIMEOUT') {
      setDraftError('草稿结构化超过时限，助手原始回答未被执行；可再次转换或改用手工临床操作。');
      return;
    }
    setDraftError(cause instanceof Error ? cause.message : '操作草稿处理失败。');
  };

  const generateDraftMutation = useMutation({
    mutationFn: async (message: AssistantMessage) => {
      const latest = actionDrafts.data ?? (await actionDrafts.refetch()).data;
      if (!latest || !message.sessionId) throw new Error('助手会话或患者状态尚未就绪。');
      return generateAssistantActionDrafts(patientId, {
        session_id: message.sessionId,
        source_text: message.content,
        citations: message.citations ?? [],
        expected_version: latest.state_version,
      });
    },
    onSuccess: async (result) => {
      setDraftFeedback(`已生成 ${result.drafts.length} 条待医生审核的操作草稿。`);
      setDraftError('');
      await refreshClinicalState();
    },
    onError: reportDraftError,
  });

  const updateDraftMutation = useMutation({
    mutationFn: async (draft: AssistantActionDraft) => {
      const latest = actionDrafts.data ?? (await actionDrafts.refetch()).data;
      if (!latest) throw new Error('患者状态尚未就绪。');
      return updateAssistantActionDraft(patientId, draft.id, {
        payload: payloadFromFields(draft.draft_type, draftFields),
        rationale: draftFields.rationale?.trim() ?? '',
        expected_version: latest.state_version,
      });
    },
    onSuccess: async () => {
      setEditingDraft(null);
      setDraftFeedback('操作草稿已保存，批准前仍不会执行。');
      setDraftError('');
      await refreshClinicalState();
    },
    onError: reportDraftError,
  });

  const decideDraftMutation = useMutation({
    mutationFn: async (next: DraftDecision) => {
      const latest = actionDrafts.data ?? (await actionDrafts.refetch()).data;
      if (!latest) throw new Error('患者状态尚未就绪。');
      return decideAssistantActionDraft(patientId, next.draft.id, next.action, {
        comment: decisionComment.trim(),
        expected_version: latest.state_version,
      });
    },
    onSuccess: async (_result, next) => {
      setDecision(null);
      setDecisionComment('');
      setDraftFeedback(next.action === 'approve' ? '草稿已批准并生成正式临床记录。' : '草稿已驳回，未生成临床记录。');
      setDraftError('');
      await refreshClinicalState();
    },
    onError: reportDraftError,
  });

  useEffect(() => {
    streamController.current?.abort();
    streamController.current = undefined;
    setInput('');
    setMessages([]);
    setSessionId(undefined);
    setIsStreaming(false);
    setError('');
    setEditingDraft(null);
    setDecision(null);
    setDraftFeedback('');
    setDraftError('');
  }, [assistantMode, patientId]);

  useEffect(() => {
    if (requestedMode) setAssistantMode(requestedMode);
  }, [requestedMode]);

  useEffect(() => () => streamController.current?.abort(), []);

  const stopStreaming = () => streamController.current?.abort();
  const restoreSession = async (id: string) => { const session = await fetchAssistantSession(id); if (session.assistant_mode !== assistantMode || session.patient_id !== patientId) { setError('该会话的助手模式或患者上下文不匹配，无法恢复。'); return; } setSessionId(id); setMessages(session.history.map((item, index) => ({ id: `${id}-${index}`, role: item.role, content: item.content, completed: item.role === 'assistant', sessionId: id }))); setShowSessions(false); };
  const clearSession = async () => { if (!sessionId) return; await resetAssistantSession(sessionId); setMessages([]); await sessions.refetch(); };

  const sendMessage = async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || isStreaming) return;

    const assistantMessageId = `assistant-${Date.now()}`;
    const controller = new AbortController();
    streamController.current = controller;
    setInput('');
    setError('');
    setIsStreaming(true);
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: 'user', content: message },
      { id: assistantMessageId, role: 'assistant', content: '' },
    ]);

    const updateAssistant = (event: AssistantStreamEvent) => {
      setMessages((current) => current.map((item) => {
        if (item.id !== assistantMessageId) return item;
        if (event.type === 'token') return { ...item, content: `${item.content}${event.token}` };
        return { ...item, sources: event.sources, citations: event.citations, completed: true, sessionId: event.sessionId ?? sessionId };
      }));
      if (event.type === 'complete' && event.sessionId) setSessionId(event.sessionId);
    };

    try {
      await streamAssistantChat({ message, assistantMode, patientId, sessionId, publicAccess }, updateAssistant, controller.signal);
    } catch (cause) {
      if (controller.signal.aborted) {
        setMessages((current) => current.filter((item) => item.id !== assistantMessageId || Boolean(item.content)));
      } else {
        setMessages((current) => current.filter((item) => item.id !== assistantMessageId));
        setError(cause instanceof Error ? cause.message : '智能助手响应失败，请稍后重试');
      }
    } finally {
      if (streamController.current === controller) {
        streamController.current = undefined;
        setIsStreaming(false);
      }
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void sendMessage(input);
  };

  const startEditDraft = (draft: AssistantActionDraft) => {
    setEditingDraft(draft);
    setDraftFields(fieldsFromDraft(draft));
    setDraftError('');
  };

  const startDecision = (draft: AssistantActionDraft, action: DraftDecision['action']) => {
    setDecision({ draft, action });
    setDecisionComment('');
    setDraftError('');
  };

  return (
    <>
    <Card variant="outlined" sx={{ borderRadius: 1 }}>
      <Box sx={{ px: 1.75, py: 1.25, display: 'flex', alignItems: 'center', gap: 0.75, borderBottom: open ? '1px solid' : 0, borderColor: 'divider' }}>
        <Bot size={18} />
        <Typography variant="subtitle2" fontWeight={600} sx={{ flex: 1 }}>{panelTitle}</Typography>
        {!publicAccess ? <Tooltip title="会话记录"><IconButton size="small" aria-label="会话记录" onClick={() => setShowSessions(true)}><History size={17} /></IconButton></Tooltip> : null}
        {sessionId && !publicAccess ? <Tooltip title="清空当前会话"><IconButton size="small" aria-label="清空当前会话" onClick={() => void clearSession()}><RotateCcw size={17} /></IconButton></Tooltip> : null}
        <Tooltip title={open ? `收起${panelTitle}` : `展开${panelTitle}`}>
          <IconButton size="small" aria-label={open ? `收起${panelTitle}` : `展开${panelTitle}`} onClick={() => setOpen((value) => !value)}>
            {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </IconButton>
        </Tooltip>
      </Box>
      {open ? <Box sx={{ p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
        {modes.length > 1 ? <ToggleButtonGroup
          exclusive
          size="small"
          value={assistantMode}
          onChange={(_, value: AssistantMode | null) => { if (value) setAssistantMode(value); }}
          aria-label="选择助手"
          sx={{ alignSelf: 'flex-start', '& .MuiToggleButton-root': { px: 1.25, py: 0.45 } }}
        >
          {modes.map((mode) => <ToggleButton key={mode} value={mode}>{ASSISTANT_META[mode].shortName}</ToggleButton>)}
        </ToggleButtonGroup> : null}
        <Typography variant="caption" color="text.secondary">{publicAccess ? '不接入患者病历；紧急或持续不适请及时就医。' : patientId ? '回答仅作为临床决策支持，需结合原始记录与临床判断。' : '回答仅作为临床工作支持，需结合规范、原始记录与临床判断。'}</Typography>
        {error ? <Alert severity="error" action={<IconButton aria-label="关闭错误提示" size="small" onClick={() => setError('')}><X size={16} /></IconButton>}>{error}</Alert> : null}
        {messages.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, maxHeight: 360, overflowY: 'auto', pr: 0.5 }}>
          {messages.map((message) => <ChatMessage
            key={message.id}
            message={message}
            streaming={isStreaming && message.role === 'assistant' && !message.content}
            onCreateDraft={canManageDrafts ? () => generateDraftMutation.mutate(message) : undefined}
            drafting={generateDraftMutation.isPending}
          />)}
        </Box> : null}
        {!messages.length && quickQuestions.data?.questions.length ? <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
          {quickQuestions.data.questions.slice(0, 4).map((question) => <Chip key={question} label={question} onClick={() => void sendMessage(question)} disabled={isStreaming} variant="outlined" size="small" sx={{ height: 'auto', '& .MuiChip-label': { display: 'block', whiteSpace: 'normal', py: 0.5 } }} />)}
        </Box> : null}
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.75 }}>
          <TextField
            placeholder={modeMeta.placeholder}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            minRows={2}
            maxRows={4}
            multiline
            fullWidth
            disabled={isStreaming}
            inputRef={inputRef}
            slotProps={{ htmlInput: { 'aria-label': `向${panelTitle}提问` } }}
          />
          {isStreaming ? <Tooltip title="停止生成"><IconButton aria-label="停止生成" color="error" onClick={stopStreaming}><Square size={17} /></IconButton></Tooltip> : <Tooltip title="发送问题" describeChild><span><IconButton aria-label="发送问题" color="primary" type="submit" disabled={!input.trim()}><Send size={18} /></IconButton></span></Tooltip>}
        </Box>
        {canManageDrafts ? <>
          <Divider />
          <ActionDraftWorkspace
            drafts={actionDrafts.data?.drafts ?? []}
            loading={actionDrafts.isLoading}
            loadError={Boolean(actionDrafts.error)}
            feedback={draftFeedback}
            error={draftError}
            onDismissFeedback={() => setDraftFeedback('')}
            onDismissError={() => setDraftError('')}
            onEdit={startEditDraft}
            onDecision={startDecision}
            onStartDraft={() => inputRef.current?.focus()}
            onOpenClinicalRecord={onOpenClinicalRecord}
          />
        </> : null}
      </Box> : null}
    </Card>
    <Dialog open={showSessions} onClose={() => setShowSessions(false)} fullWidth maxWidth="sm"><DialogTitle>我的助手会话</DialogTitle><DialogContent>{sessions.isLoading ? <CircularProgress size={22} /> : sessions.error ? <Alert severity="error">会话列表加载失败。</Alert> : !sessions.data?.sessions.length ? <Typography color="text.secondary">暂无可恢复会话。</Typography> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>{sessions.data.sessions.map((session) => <Button key={session.session_id} variant="outlined" color="inherit" onClick={() => void restoreSession(session.session_id)} sx={{ justifyContent: 'flex-start', textAlign: 'left', textTransform: 'none' }}><Box><Typography variant="body2">{ASSISTANT_META[session.assistant_mode].name}{session.patient_id ? ` · 患者 ${session.patient_id}` : ' · 通用咨询'}</Typography><Typography variant="caption" color="text.secondary">{session.message_count} 条消息</Typography></Box></Button>)}</Box>}</DialogContent></Dialog>
    <DraftEditDialog
      draft={editingDraft}
      fields={draftFields}
      pending={updateDraftMutation.isPending}
      onChange={setDraftFields}
      onClose={() => setEditingDraft(null)}
      onSave={() => editingDraft && updateDraftMutation.mutate(editingDraft)}
    />
    <DraftDecisionDialog
      decision={decision}
      comment={decisionComment}
      pending={decideDraftMutation.isPending}
      onCommentChange={setDecisionComment}
      onClose={() => setDecision(null)}
      onConfirm={() => decision && decideDraftMutation.mutate(decision)}
    />
    </>
  );
}

function ChatMessage({ message, streaming, onCreateDraft, drafting }: { message: AssistantMessage; streaming: boolean; onCreateDraft?: () => void; drafting: boolean }) {
  const isUser = message.role === 'user';
  return <Box sx={{ alignSelf: isUser ? 'flex-end' : 'stretch', maxWidth: isUser ? '86%' : '100%' }}>
    <Box sx={{ px: 1.25, py: 1, bgcolor: isUser ? 'primary.main' : 'action.hover', color: isUser ? 'primary.contrastText' : 'text.primary', borderRadius: 1, whiteSpace: 'pre-wrap' }}>
      <Typography variant="body2" sx={{ lineHeight: 1.65 }}>{message.content || (streaming ? <CircularProgress size={14} color="inherit" /> : '未返回文本内容')}</Typography>
    </Box>
    {!isUser && (message.sources?.length || message.citations?.length) ? <Box sx={{ mt: 0.75, px: 0.25 }}>
      <Typography variant="caption" color="text.secondary">本次问答引用</Typography>
      {message.sources?.length ? <Typography variant="caption" color="text.secondary" display="block">{message.sources.join(' · ')}</Typography> : null}
      {message.citations?.map((citation, index) => <Box key={`${citation.title ?? citation.source ?? 'citation'}-${index}`} sx={{ mt: 0.5, borderLeft: '2px solid', borderColor: 'divider', pl: 0.75 }}>
        <Typography variant="caption" fontWeight={600}>{String(citation.title ?? citation.source ?? `引用 ${index + 1}`)}</Typography>
        <Typography variant="caption" color="text.secondary" display="block">{citationText(citation)}</Typography>
      </Box>)}
    </Box> : null}
    {!isUser && message.completed && onCreateDraft ? <Button size="small" variant="text" startIcon={drafting ? <CircularProgress size={13} /> : <ClipboardPlus size={14} />} onClick={onCreateDraft} disabled={drafting || !message.content} sx={{ mt: 0.5, textTransform: 'none' }}>转为操作草稿</Button> : null}
  </Box>;
}

function ActionDraftWorkspace({ drafts, loading, loadError, feedback, error, onDismissFeedback, onDismissError, onEdit, onDecision, onStartDraft, onOpenClinicalRecord }: {
  drafts: AssistantActionDraft[];
  loading: boolean;
  loadError: boolean;
  feedback: string;
  error: string;
  onDismissFeedback: () => void;
  onDismissError: () => void;
  onEdit: (draft: AssistantActionDraft) => void;
  onDecision: (draft: AssistantActionDraft, action: DraftDecision['action']) => void;
  onStartDraft: () => void;
  onOpenClinicalRecord?: (draft: AssistantActionDraft) => void;
}) {
  const sorted = [...drafts].sort((left, right) => {
    if (left.status === 'pending' && right.status !== 'pending') return -1;
    if (left.status !== 'pending' && right.status === 'pending') return 1;
    return right.updated_at.localeCompare(left.updated_at);
  });
  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}><ClipboardPlus size={16} /><Typography variant="subtitle2">AI 操作草稿</Typography><Chip size="small" variant="outlined" label={`${drafts.filter((draft) => draft.status === 'pending').length} 条待审核`} /></Box>
    {feedback ? <Alert severity="success" action={<IconButton size="small" aria-label="关闭草稿成功提示" onClick={onDismissFeedback}><X size={15} /></IconButton>}>{feedback}</Alert> : null}
    {error ? <Alert severity="error" action={<IconButton size="small" aria-label="关闭草稿错误提示" onClick={onDismissError}><X size={15} /></IconButton>}>{error}</Alert> : null}
    {loading ? <CircularProgress size={18} /> : loadError ? <Alert severity="warning">操作草稿暂时无法加载。</Alert> : sorted.length === 0 ? <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}><Typography variant="body2" color="text.secondary">暂无待审核草稿</Typography><Button size="small" variant="outlined" startIcon={<ClipboardPlus size={14} />} onClick={onStartDraft} sx={{ textTransform: 'none' }}>向助手提问</Button></Box> : <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {sorted.map((draft) => <Box key={draft.id} sx={{ borderLeft: '3px solid', borderColor: draft.status === 'pending' ? 'warning.main' : draft.status === 'approved' ? 'success.main' : 'divider', pl: 1.25, py: 0.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}><Typography variant="body2" fontWeight={600}>{draftTypeLabel(draft.draft_type)}</Typography><Chip size="small" variant="outlined" color={draft.status === 'approved' ? 'success' : draft.status === 'rejected' ? 'default' : 'warning'} label={draftStatusLabel(draft.status)} /></Box>
        <Typography variant="body2" sx={{ mt: 0.35 }}>{draftSummary(draft)}</Typography>
        {draft.rationale ? <Typography variant="caption" color="text.secondary" display="block">依据：{draft.rationale}</Typography> : null}
        {draft.execution ? <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap', mt: 0.25 }}><Typography variant="caption" color="success.main">已生成正式记录 · {draft.execution.status}</Typography>{onOpenClinicalRecord ? <Button size="small" variant="text" onClick={() => onOpenClinicalRecord(draft)} sx={{ textTransform: 'none' }}>查看正式记录</Button> : null}</Box> : null}
        {draft.status === 'pending' ? <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
          <Button size="small" variant="text" startIcon={<Pencil size={13} />} onClick={() => onEdit(draft)} sx={{ textTransform: 'none' }}>编辑</Button>
          <Button size="small" variant="text" color="success" startIcon={<Check size={13} />} onClick={() => onDecision(draft, 'approve')} sx={{ textTransform: 'none' }}>批准并执行</Button>
          <Button size="small" variant="text" color="error" startIcon={<XCircle size={13} />} onClick={() => onDecision(draft, 'reject')} sx={{ textTransform: 'none' }}>驳回</Button>
        </Box> : null}
      </Box>)}
    </Box>}
  </Box>;
}

function DraftEditDialog({ draft, fields, pending, onChange, onClose, onSave }: {
  draft: AssistantActionDraft | null;
  fields: Record<string, string>;
  pending: boolean;
  onChange: (fields: Record<string, string>) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const setField = (key: string) => (event: ChangeEvent<HTMLInputElement>) => onChange({ ...fields, [key]: event.target.value });
  return <Dialog open={Boolean(draft)} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>编辑{draft ? draftTypeLabel(draft.draft_type) : '操作草稿'}</DialogTitle>
    <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>
      <Alert severity="info">保存只更新草稿，不会生成医嘱、检查或随访任务。</Alert>
      {draft?.draft_type === 'medication_order' ? <><TextField label="药品名称" value={fields.medication ?? ''} onChange={setField('medication')} required /><TextField label="剂量" value={fields.dose ?? ''} onChange={setField('dose')} required /><TextField label="频次" value={fields.frequency ?? ''} onChange={setField('frequency')} required /><TextField label="给药途径" value={fields.route ?? ''} onChange={setField('route')} /><TextField label="适应证" value={fields.indication ?? ''} onChange={setField('indication')} /></> : null}
      {draft?.draft_type === 'investigation_order' ? <><TextField label="检查或检验项目" value={fields.test_name ?? ''} onChange={setField('test_name')} required /><TextField select label="优先级" value={fields.priority ?? 'routine'} onChange={setField('priority')}><MenuItem value="routine">常规</MenuItem><MenuItem value="urgent">紧急</MenuItem></TextField><TextField label="检查原因" value={fields.reason ?? ''} onChange={setField('reason')} multiline minRows={2} required /><TextField label="计划时间" value={fields.timing ?? ''} onChange={setField('timing')} /><TextField label="执行注意事项" value={fields.instructions ?? ''} onChange={setField('instructions')} multiline minRows={2} /></> : null}
      {draft?.draft_type === 'follow_up_task' ? <><TextField label="随访事项" value={fields.title ?? ''} onChange={setField('title')} required /><TextField label="随访时间" type="datetime-local" value={toLocalDateTime(fields.due_at ?? '')} onChange={setField('due_at')} InputLabelProps={{ shrink: true }} required /><TextField label="负责人" value={fields.assignee ?? ''} onChange={setField('assignee')} /></> : null}
      {draft?.draft_type === 'mdt_request' ? <><TextField label="会诊原因" value={fields.reason ?? ''} onChange={setField('reason')} multiline minRows={2} required /><TextField label="会诊专科（用顿号或逗号分隔）" value={fields.specialties ?? ''} onChange={setField('specialties')} required /></> : null}
      {draft?.draft_type === 'education_plan' ? <><TextField label="宣教主题" value={fields.topic ?? ''} onChange={setField('topic')} required /><TextField select label="宣教对象" value={fields.recipient ?? 'patient'} onChange={setField('recipient')}><MenuItem value="patient">患者</MenuItem><MenuItem value="family">家属</MenuItem><MenuItem value="caregiver">照护者</MenuItem></TextField><TextField label="宣教要点（用顿号或逗号分隔）" value={fields.key_points ?? ''} onChange={setField('key_points')} multiline minRows={2} /></> : null}
      <TextField label="建议理由" value={fields.rationale ?? ''} onChange={setField('rationale')} multiline minRows={2} />
    </DialogContent>
    <DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" onClick={onSave} disabled={!draft || !canSaveDraft(draft.draft_type, fields) || pending} startIcon={pending ? <CircularProgress size={14} color="inherit" /> : undefined}>保存草稿</Button></DialogActions>
  </Dialog>;
}

function DraftDecisionDialog({ decision, comment, pending, onCommentChange, onClose, onConfirm }: {
  decision: DraftDecision | null;
  comment: string;
  pending: boolean;
  onCommentChange: (comment: string) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const approving = decision?.action === 'approve';
  return <Dialog open={Boolean(decision)} onClose={onClose} fullWidth maxWidth="xs">
    <DialogTitle>{approving ? '批准并执行操作草稿' : '驳回操作草稿'}</DialogTitle>
    <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: '12px !important' }}>
      <Alert severity={approving ? 'warning' : 'info'}>{approving ? '批准后将立即生成正式临床记录，AI 不会绕过本次人工确认。' : '驳回后不会生成任何临床记录。'}</Alert>
      {decision ? <><Typography variant="subtitle2">{draftTypeLabel(decision.draft.draft_type)}</Typography><Typography variant="body2">{draftSummary(decision.draft)}</Typography></> : null}
      <TextField label={approving ? '审核意见' : '驳回原因'} value={comment} onChange={(event) => onCommentChange(event.target.value)} multiline minRows={2} required />
    </DialogContent>
    <DialogActions><Button onClick={onClose} disabled={pending}>取消</Button><Button variant="contained" color={approving ? 'primary' : 'error'} onClick={onConfirm} disabled={!comment.trim() || pending} startIcon={pending ? <CircularProgress size={14} color="inherit" /> : undefined}>{approving ? '确认批准并执行' : '确认驳回'}</Button></DialogActions>
  </Dialog>;
}

function fieldsFromDraft(draft: AssistantActionDraft): Record<string, string> {
  return Object.fromEntries([
    ...Object.entries(draft.payload).map(([key, value]) => [key, Array.isArray(value) ? value.join('、') : String(value ?? '')]),
    ['rationale', draft.rationale ?? ''],
  ]);
}

function payloadFromFields(type: AssistantActionDraft['draft_type'], fields: Record<string, string>): Record<string, string | string[] | null> {
  if (type === 'medication_order') return { medication: fields.medication?.trim() ?? '', dose: fields.dose?.trim() ?? '', frequency: fields.frequency?.trim() ?? '', route: fields.route?.trim() || 'PO', indication: fields.indication?.trim() ?? '' };
  if (type === 'investigation_order') return { test_name: fields.test_name?.trim() ?? '', priority: fields.priority || 'routine', reason: fields.reason?.trim() ?? '', timing: fields.timing?.trim() ?? '', instructions: fields.instructions?.trim() ?? '' };
  if (type === 'follow_up_task') return { title: fields.title?.trim() ?? '', due_at: normalizeDateTime(fields.due_at ?? ''), assignee: fields.assignee?.trim() || null };
  if (type === 'mdt_request') return { reason: fields.reason?.trim() ?? '', specialties: splitItems(fields.specialties) };
  return { topic: fields.topic?.trim() ?? '', recipient: fields.recipient || 'patient', key_points: splitItems(fields.key_points) };
}

function canSaveDraft(type: AssistantActionDraft['draft_type'], fields: Record<string, string>): boolean {
  if (type === 'medication_order') return Boolean(fields.medication?.trim() && fields.dose?.trim() && fields.frequency?.trim());
  if (type === 'investigation_order') return Boolean(fields.test_name?.trim() && fields.reason?.trim());
  if (type === 'follow_up_task') return Boolean(fields.title?.trim() && fields.due_at?.trim());
  if (type === 'mdt_request') return Boolean(fields.reason?.trim() && splitItems(fields.specialties).length);
  return Boolean(fields.topic?.trim());
}

function draftTypeLabel(type: AssistantActionDraft['draft_type']): string {
  return { medication_order: '用药医嘱草稿', investigation_order: '检查医嘱草稿', follow_up_task: '随访任务草稿', mdt_request: 'MDT 会诊草稿', education_plan: '患者宣教计划' }[type];
}

function draftStatusLabel(status: AssistantActionDraft['status']): string {
  return { pending: '待审核', approved: '已批准', rejected: '已驳回' }[status];
}

function draftSummary(draft: AssistantActionDraft): string {
  const payload = draft.payload;
  if (draft.draft_type === 'medication_order') return `${payload.medication ?? ''} ${payload.dose ?? ''} · ${payload.frequency ?? ''} · ${payload.route ?? 'PO'}`;
  if (draft.draft_type === 'investigation_order') return `${payload.test_name ?? ''} · ${payload.priority === 'urgent' ? '紧急' : '常规'} · ${payload.timing || '时间待安排'}`;
  if (draft.draft_type === 'follow_up_task') return `${payload.title ?? ''} · ${payload.due_at ?? ''}${payload.assignee ? ` · ${payload.assignee}` : ''}`;
  if (draft.draft_type === 'mdt_request') return `${payload.reason ?? ''} · ${formatList(payload.specialties)}`;
  return `${payload.topic ?? ''} · ${formatList(payload.key_points) || '待补充宣教要点'}`;
}

function splitItems(value?: string): string[] { return (value ?? '').split(/[、,，]/).map((item) => item.trim()).filter(Boolean); }
function formatList(value: unknown): string { return Array.isArray(value) ? value.join('、') : String(value ?? ''); }

function toLocalDateTime(value: string): string {
  return value ? value.slice(0, 16) : '';
}

function normalizeDateTime(value: string): string {
  if (!value) return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function citationText(citation: AssistantCitation): string {
  return String(citation.excerpt ?? citation.content ?? citation.citation ?? '未提供引用片段');
}
