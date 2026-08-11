import { Alert, Box, Button, ButtonBase, Card, Chip, CircularProgress, Dialog, DialogContent, DialogTitle, Divider, MenuItem, Select, TextField, Typography } from '@mui/material';
import { BookOpenCheck, Database, ExternalLink, Network, RefreshCw, Route, Search, ShieldCheck, X } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import EvidenceGraphCanvas from '@/components/admin/EvidenceGraphCanvas';
import { useDiseaseEvidenceGraph, useDiseaseEvidenceGraphVisualization, useDiseaseTemplates, useEvidenceGraphStatus } from '@/hooks/use-admin';
import { rebuildEvidenceGraph } from '@/services/admin-service';
import type { DiseaseEvidenceGraphResponse, EvidenceGraphEvidence, EvidenceGraphRule } from '@/types/evidence-graph';
import { clinicalRuleKeyLabel, clinicalRuleText, EVIDENCE_RELATION_LABELS, ruleDisplayText } from '@/utils/evidence-graph-utils';

type RelationFilter = 'all' | 'HAS_DISCHARGE_CRITERION' | 'HAS_MEDICATION_RULE' | 'HAS_MONITORING_RULE' | 'HAS_CARE_TASK';
type PathStep = 'disease' | 'evidence' | 'rules' | 'handoff';

export default function EvidenceGraphPanel() {
  const queryClient = useQueryClient();
  const [selectedDisease, setSelectedDisease] = useState('');
  const [relation, setRelation] = useState<RelationFilter>('all');
  const [activeStep, setActiveStep] = useState<PathStep>('disease');
  const [search, setSearch] = useState('');
  const [showEvidence, setShowEvidence] = useState(true);
  const [selectedRule, setSelectedRule] = useState<EvidenceGraphRule | null>(null);
  const status = useEvidenceGraphStatus();
  const templates = useDiseaseTemplates();
  const diseaseId = selectedDisease || templates.data?.templates[0]?.disease_id || '';
  const template = templates.data?.templates.find((item) => item.disease_id === diseaseId);
  const disease = useDiseaseEvidenceGraph(diseaseId);
  const visualization = useDiseaseEvidenceGraphVisualization(diseaseId, status.data?.reachable === true);
  const rebuild = useMutation({
    mutationFn: rebuildEvidenceGraph,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'evidence-graph'] });
    },
  });

  const filtered = useMemo(() => filterGraph(disease.data, relation, search), [disease.data, relation, search]);
  const ruleGroups = useMemo(() => {
    const groups = new Map<string, EvidenceGraphRule[]>();
    for (const rule of filtered.rules) groups.set(rule.relation, [...(groups.get(rule.relation) ?? []), rule]);
    return Array.from(groups.entries());
  }, [filtered.rules]);

  if (status.isLoading || templates.isLoading) return <Card variant="outlined" sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1 }}><CircularProgress size={20} /><Typography variant="body2" color="text.secondary">正在加载证据图谱...</Typography></Card>;
  if (status.error || templates.error) return <Alert severity="warning" action={<Button size="small" color="inherit" onClick={() => { void status.refetch(); void templates.refetch(); }}>重试</Button>}>证据图谱状态暂时不可用，请稍后重试。</Alert>;
  const graph = status.data;
  if (!graph) return null;

  return <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <Alert severity={graph.reachable ? 'success' : 'warning'} icon={<ShieldCheck size={18} />} action={<Button size="small" color="inherit" startIcon={<RefreshCw size={15} />} onClick={() => rebuild.mutate()} disabled={rebuild.isPending}>{rebuild.isPending ? '重建中' : '重建图谱'}</Button>}>
      {graph.reachable ? 'Neo4j 图谱已连接。重建只同步版本化知识与病种模板，不包含患者数据。' : 'Neo4j 图谱当前不可用，临床工作流与现有 RAG 不受影响。'}
    </Alert>
    {rebuild.error ? <Alert severity="error" action={<Button size="small" color="inherit" onClick={() => rebuild.mutate()}>重试</Button>}>图谱重建失败：{rebuild.error instanceof Error ? rebuild.error.message : '服务暂时不可用'}</Alert> : null}

    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(4, minmax(0, 1fr))' }, gap: 1.25 }}>
      <Metric icon={<Database size={17} />} label="证据节点" value={graph.nodes.Evidence ?? 0} />
      <Metric icon={<Route size={17} />} label="规则节点" value={graph.nodes.ClinicalRule ?? 0} />
      <Metric icon={<Network size={17} />} label="关系数量" value={graph.relationships} />
      <Metric icon={<ShieldCheck size={17} />} label="运行状态" value={graph.reachable ? '已连接' : '待连接'} tone={graph.reachable ? 'success' : 'warning'} />
    </Box>

    <Card variant="outlined" sx={{ overflow: 'hidden' }}>
      <Box sx={{ px: 1.75, py: 1.35, borderBottom: '1px solid', borderColor: 'divider', display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Network size={18} /><Box><Typography variant="subtitle2" fontWeight={600}>病种证据路径</Typography><Typography variant="caption" color="text.secondary">按病种查看证据来源、临床规则和出院随访约束</Typography></Box>
        <Select size="small" value={diseaseId} onChange={(event) => { setSelectedDisease(event.target.value); setRelation('all'); setActiveStep('disease'); setShowEvidence(true); setSearch(''); }} sx={{ ml: { md: 'auto' }, minWidth: 220 }} inputProps={{ 'aria-label': '选择病种图谱' }}>
          {templates.data?.templates.map((item) => <MenuItem key={item.disease_id} value={item.disease_id}>{item.name} · {item.department}</MenuItem>)}
        </Select>
      </Box>
      {!graph.reachable ? <Box sx={{ p: 2 }}><Typography variant="body2" color="text.secondary">图谱恢复连接后即可查看病种关联。</Typography></Box> : disease.isLoading || visualization.isLoading ? <Box sx={{ p: 2, display: 'flex', gap: 1, alignItems: 'center' }}><CircularProgress size={18} /><Typography variant="body2" color="text.secondary">正在解析病种路径...</Typography></Box> : disease.error ? <Box sx={{ p: 2 }}><Alert severity="warning" action={<Button size="small" color="inherit" onClick={() => void disease.refetch()}>重试</Button>}>病种路径暂时不可用。</Alert></Box> : <Box sx={{ p: 1.75 }}>
        {visualization.error ? <Alert severity="warning" action={<Button size="small" color="inherit" onClick={() => void visualization.refetch()}>重试</Button>}>图谱投影暂时不可用，仍可查看下方证据与规则路径。</Alert> : null}
        {visualization.data ? <EvidenceGraphCanvas graph={visualization.data} /> : null}
        <PathSteps activeStep={activeStep} evidenceCount={filtered.evidence.length} ruleCount={filtered.rules.length} onSelect={(step) => {
          setActiveStep(step);
          setRelation(step === 'handoff' ? 'HAS_DISCHARGE_CRITERION' : 'all');
          setShowEvidence(step === 'disease' || step === 'evidence');
        }} />
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) 210px' }, gap: 1, mt: 1.5 }}>
          <TextField size="small" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索规则、适用条件或证据主题" slotProps={{ input: { startAdornment: <Search size={16} style={{ marginRight: 8 }} /> } }} />
          <Button variant={showEvidence ? 'contained' : 'outlined'} size="small" startIcon={<BookOpenCheck size={15} />} onClick={() => setShowEvidence((value) => !value)}>{showEvidence ? '已显示证据来源' : '显示证据来源'}</Button>
        </Box>
        {template ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>当前路径：{template.name} · {template.department} · {filtered.rules.length} 条规则 · {filtered.evidence.length} 条证据</Typography> : null}
        {showEvidence ? <EvidenceSourceList evidence={filtered.evidence} /> : null}
        <Divider sx={{ my: 1.5 }} />
        {ruleGroups.length ? <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 1.25 }}>{ruleGroups.map(([groupRelation, rules]) => <RuleGroup key={groupRelation} relation={groupRelation} rules={rules} onSelect={setSelectedRule} />)}</Box> : <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>没有匹配的规则，请调整病种或搜索条件。</Typography>}
      </Box>}
    </Card>
    <RuleDetailDialog rule={selectedRule} evidence={disease.data?.evidence ?? []} onClose={() => setSelectedRule(null)} />
  </Box>;
}

function filterGraph(data: DiseaseEvidenceGraphResponse | undefined, relation: RelationFilter, search: string) {
  const query = search.trim().toLowerCase();
  const matches = (value: string) => !query || value.toLowerCase().includes(query);
  return {
    rules: (data?.rules ?? []).filter((rule) => (relation === 'all' || rule.relation === relation) && matches(`${rule.key} ${rule.content} ${clinicalRuleText(rule.key)} ${ruleDisplayText(rule)}`)),
    evidence: (data?.evidence ?? []).filter((item) => matches(`${item.topic} ${item.text} ${item.source} ${item.category}`)),
  };
}

function Metric({ icon, label, value, tone = 'primary' }: { icon: React.ReactNode; label: string; value: string | number; tone?: 'primary' | 'success' | 'warning' }) {
  return <Card variant="outlined" sx={{ p: 1.5 }}><Box sx={{ display: 'flex', gap: 0.75, alignItems: 'center', color: `${tone}.main` }}><Box sx={{ width: 28, height: 28, borderRadius: 1, display: 'grid', placeItems: 'center', bgcolor: `${tone}.light` }}>{icon}</Box><Typography variant="caption" color="text.secondary">{label}</Typography></Box><Typography variant="h5" sx={{ mt: 0.75 }}>{value}</Typography></Card>;
}

function PathSteps({ activeStep, evidenceCount, ruleCount, onSelect }: { activeStep: PathStep; evidenceCount: number; ruleCount: number; onSelect: (value: PathStep) => void }) {
  const items: Array<{ label: string; value: PathStep; count?: number }> = [
    { label: '病种', value: 'disease' },
    { label: '证据来源', value: 'evidence', count: evidenceCount },
    { label: '临床规则', value: 'rules', count: ruleCount },
    { label: '出院与随访', value: 'handoff' },
  ];
  return <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(4, minmax(0, 1fr))' }, gap: 0.75 }}>{items.map((item, index) => {
    const selected = activeStep === item.value;
    return <ButtonBase key={item.label} onClick={() => onSelect(item.value)} sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0, textAlign: 'left' }}><Box sx={{ flex: 1, minHeight: 52, px: 1, py: 0.8, border: '1px solid', borderColor: selected ? 'primary.main' : 'divider', borderRadius: 1, bgcolor: selected ? 'primary.light' : 'background.default', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}><Typography variant="caption" fontWeight={600}>{item.label}</Typography>{item.count != null ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{item.count} 项</Typography> : null}</Box>{index < items.length - 1 ? <Typography color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>→</Typography> : null}</ButtonBase>;
  })}</Box>;
}

function EvidenceSourceList({ evidence }: { evidence: EvidenceGraphEvidence[] }) {
  return <Box sx={{ mt: 1.5 }}><Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mb: 0.75 }}><BookOpenCheck size={15} /><Typography variant="caption" color="text.secondary" fontWeight={600}>关联证据来源</Typography><Chip size="small" label={evidence.length} sx={{ ml: 0.25 }} /></Box>{evidence.length ? <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 0.75 }}>{evidence.map((item) => <Box key={item.id} sx={{ p: 1, minHeight: 112, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}><Typography variant="body2" fontWeight={600}>{item.topic}</Typography><Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.35 }}>{item.source} · {item.category || '临床证据'}{item.version ? ` · ${item.version}` : ''}</Typography><Typography variant="caption" sx={{ display: 'block', mt: 0.65, lineHeight: 1.5 }}>{item.text}</Typography></Box>)}</Box> : <Typography variant="caption" color="text.secondary">当前筛选条件下没有匹配的证据来源。</Typography>}</Box>;
}

function RuleGroup({ relation, rules, onSelect }: { relation: string; rules: EvidenceGraphRule[]; onSelect: (rule: EvidenceGraphRule) => void }) {
  const label = EVIDENCE_RELATION_LABELS[relation] ?? '临床规则';
  return <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }}><Box sx={{ minHeight: 40, px: 1.25, py: 0.85, bgcolor: 'background.default', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}><Typography variant="caption" fontWeight={600}>{label}</Typography><Chip size="small" label={rules.length} /></Box><Box sx={{ px: 1.25, py: 0.5 }}>{rules.map((rule, index) => <ButtonBase key={`${rule.key}:${index}`} onClick={() => onSelect(rule)} sx={{ display: 'block', width: '100%', minHeight: 66, py: 0.8, textAlign: 'left', borderBottom: index === rules.length - 1 ? 0 : '1px solid', borderColor: 'divider' }}><Typography variant="body2" fontWeight={600}>{ruleDisplayText(rule)}</Typography>{clinicalRuleKeyLabel(rule.key) ? <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.2 }}>{clinicalRuleKeyLabel(rule.key)}</Typography> : null}<Typography variant="caption" color="primary.main" sx={{ display: 'block', mt: 0.35 }}>查看规则详情与关联证据</Typography></ButtonBase>)}</Box></Box>;
}

function RuleDetailDialog({ rule, evidence, onClose }: { rule: EvidenceGraphRule | null; evidence: EvidenceGraphEvidence[]; onClose: () => void }) {
  if (!rule) return null;
  const related = evidence.filter((item) => `${item.topic} ${item.text}`.toLowerCase().includes(rule.key.toLowerCase()) || `${item.topic} ${item.text}`.toLowerCase().includes(rule.content.toLowerCase()));
  return <Dialog open={Boolean(rule)} onClose={onClose} fullWidth maxWidth="sm"><DialogTitle sx={{ pr: 6 }}>{EVIDENCE_RELATION_LABELS[rule.relation] ?? '临床规则'}<Typography variant="body2" color="text.secondary" sx={{ mt: 0.55 }}>{ruleDisplayText(rule)}</Typography><ButtonBase aria-label="关闭规则详情" onClick={onClose} sx={{ position: 'absolute', right: 12, top: 12, p: 0.75 }}><X size={18} /></ButtonBase></DialogTitle><DialogContent dividers><Typography variant="caption" color="text.secondary">规则说明</Typography><Typography variant="body2" sx={{ mt: 0.35, lineHeight: 1.6 }}>{clinicalRuleKeyLabel(rule.key) || '根据当前病种模板维护的临床约束'}</Typography><Divider sx={{ my: 1.5 }} /><Typography variant="caption" color="text.secondary">关联证据</Typography>{related.length ? <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 0.75 }}>{related.map((item) => <Box key={item.id} sx={{ p: 1, bgcolor: 'background.default', borderRadius: 1 }}><Typography variant="body2" fontWeight={600}>{item.topic}</Typography><Typography variant="caption" color="text.secondary">{item.source}{item.version ? ` · ${item.version}` : ''}</Typography><Typography variant="body2" sx={{ mt: 0.35, lineHeight: 1.55 }}>{item.text}</Typography></Box>)}</Box> : <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>当前图谱没有与此规则直接匹配的证据片段，请结合知识库原文复核。</Typography>}<Button size="small" color="inherit" startIcon={<ExternalLink size={15} />} sx={{ mt: 1.25 }} onClick={onClose}>返回路径</Button></DialogContent></Dialog>;
}
