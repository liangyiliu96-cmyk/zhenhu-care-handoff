import AppShell from '@/components/layout/AppShell';
import AdminDataPanels from '@/components/admin/AdminDataPanels';
import NurseManagementPanel from '@/components/admin/NurseManagementPanel';
import NursePatientDrawer from '@/components/clinical/NursePatientDrawer';
import NursingEntryDialog from '@/components/clinical/NursingEntryDialog';
import NursingTaskCompletionDialog, { type NursingTaskSelection } from '@/components/clinical/NursingTaskCompletionDialog';
import { adminTabsFor, type AdminTabId } from '@/core/admin-tabs';
import WorkspaceHeader from '@/components/shared/WorkspaceHeader';
import WorkspaceWelcome from '@/components/shared/WorkspaceWelcome';
import DepartmentLeadershipStrip from '@/components/shared/DepartmentLeadershipStrip';
import { Box, Chip } from '@mui/material';
import { BookOpen, Building2, ClipboardCheck, Files, GitCompare, ListChecks, PlugZap, Settings, BarChart2, LayoutDashboard, Network, type LucideIcon } from 'lucide-react';
import { useManagementPageAuth } from '@/hooks/use-page-auth';
import { departmentDoctorRoute, departmentNurseRoute, ROUTES } from '@/core/routes';
import { fetchPatientDirectory } from '@/services/patient-directory-service';
import { directoryPatientToNurseDetail } from '@/utils/nurse-patient-utils';
import { useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import type { NursePatientDetail, NurseTask, NursingTaskItem } from '@/types/nurse-management';

const ADMIN_ICONS: Record<AdminTabId, LucideIcon> = {
  overview: LayoutDashboard,
  knowledge: BookOpen,
  evidence_graph: Network,
  templates: Files,
  organization: Building2,
  ward: BarChart2,
  nursing: ClipboardCheck,
  handoff: GitCompare,
  checklist: ListChecks,
  integrations: PlugZap,
  operations: Settings,
};

export default function AdminPage() {
  const auth = useManagementPageAuth();
  const [searchParams] = useSearchParams();
  const [selectedPatient, setSelectedPatient] = useState<NursePatientDetail | null>(null);
  const [recordingTask, setRecordingTask] = useState<NurseTask | null>(null);
  const [completingTask, setCompletingTask] = useState<NursingTaskSelection | null>(null);
  const [patientLookupError, setPatientLookupError] = useState('');
  if (auth.redirect) return auth.redirect;
  const user = auth.user!;
  const tabs = adminTabsFor(user);
  const requestedTab = searchParams.get('tab') as AdminTabId | null;
  const activeTab = tabs.some((tab) => tab.id === requestedTab) ? requestedTab! : tabs[0].id;
  const activeSection = tabs.find((tab) => tab.id === activeTab)!;
  const ActiveIcon = ADMIN_ICONS[activeTab];
  const backTo = user.department
    ? user.role === 'doctor' ? departmentDoctorRoute(user.department) : departmentNurseRoute(user.department)
    : user.role === 'doctor' ? ROUTES.workbench : ROUTES.nurse;
  const isNurseManagementTab = activeTab === 'nursing' || activeTab === 'handoff' || activeTab === 'checklist';
  const canExecuteNursing = user.role === 'nurse';
  const openNursingPatient = (task: NurseTask) => {
    setPatientLookupError('');
    setSelectedPatient({ ...task, writable: canExecuteNursing });
  };
  const openPatientById = async (patientId: string) => {
    setPatientLookupError('');
    try {
      const response = await fetchPatientDirectory({ search: patientId, limit: 10, sort: 'name' });
      const patient = response.patients.find((item) => item.patient_id === patientId);
      if (!patient) throw new Error('未找到该患者，可能已离开当前管理范围。');
      setSelectedPatient(directoryPatientToNurseDetail(patient, user.department || '当前病区'));
    } catch (error) {
      setPatientLookupError(error instanceof Error ? error.message : '患者详情暂时无法打开。');
    }
  };
  const recordNursing = (task: NurseTask) => {
    if (canExecuteNursing) setRecordingTask(task);
  };
  const completeNursingTask = (patient: NurseTask, task: NursingTaskItem) => {
    if (canExecuteNursing) setCompletingTask({ patient, task });
  };
  return (
    <AppShell title="管理控制台" backTo={backTo} backLabel={user.role === 'doctor' ? '医生工作台' : '护理看板'}>
      <Box display="flex" flexDirection="column" gap={2.5} maxWidth={1380} mx="auto" width="100%">
        <WorkspaceHeader
          eyebrow={user.role === 'doctor' ? '科室管理 / 医疗运营' : '科室管理 / 护理质量'}
          title={activeSection.label}
          description={activeSection.description}
          icon={<ActiveIcon size={20} />}
          tags={[user.department || '当前科室']}
          status={<Chip size="small" color="info" label={user.title} />}
          welcome={<WorkspaceWelcome user={user} workspace="management" />}
        />
        <DepartmentLeadershipStrip />
        {patientLookupError ? <Box sx={{ color: 'error.main', fontSize: 13 }}>{patientLookupError}</Box> : null}
        {isNurseManagementTab ? <NurseManagementPanel
          tab={activeTab}
          onOpenPatient={activeTab === 'handoff' ? (patientId) => { void openPatientById(patientId); } : undefined}
          showKpi={activeTab === 'nursing' || activeTab === 'checklist'}
          onOpenTaskPatient={activeTab === 'nursing' || activeTab === 'handoff' || activeTab === 'checklist' ? openNursingPatient : undefined}
          onRecordNursing={canExecuteNursing && (activeTab === 'nursing' || activeTab === 'checklist') ? recordNursing : undefined}
          onCompleteTask={canExecuteNursing && (activeTab === 'nursing' || activeTab === 'checklist') ? completeNursingTask : undefined}
        /> : <AdminDataPanels tab={activeTab} role={user.role} onOpenPatient={(patientId) => { void openPatientById(patientId); }} />}
      </Box>
      <NursingEntryDialog task={recordingTask} onClose={() => setRecordingTask(null)} />
      <NursingTaskCompletionDialog selection={completingTask} onClose={() => setCompletingTask(null)} />
      <NursePatientDrawer
        patient={selectedPatient}
        onClose={() => setSelectedPatient(null)}
        onRecord={recordNursing}
        onComplete={completeNursingTask}
      />
    </AppShell>
  );
}
