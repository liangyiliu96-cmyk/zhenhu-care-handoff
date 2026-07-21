import { useQuery } from '@tanstack/react-query';

import { fetchClinicalNote, fetchLabTrends, fetchNursingRecords, fetchPatientDashboard, fetchPatientEvidenceGraph, fetchPatientRounds, fetchPatientScores, fetchPatientTimeline, fetchVitalTrends } from '@/services/patient-service';

export function usePatientDashboard(patientId?: string) {
  const enabled = Boolean(patientId);
  return {
    dashboard: useQuery({ queryKey: ['patient', patientId, 'dashboard'], queryFn: () => fetchPatientDashboard(patientId!), enabled, staleTime: 20_000 }),
    scores: useQuery({ queryKey: ['patient', patientId, 'scores'], queryFn: () => fetchPatientScores(patientId!), enabled, staleTime: 20_000 }),
    timeline: useQuery({ queryKey: ['patient', patientId, 'timeline'], queryFn: () => fetchPatientTimeline(patientId!), enabled, staleTime: 30_000 }),
    rounds: useQuery({ queryKey: ['patient', patientId, 'rounds'], queryFn: () => fetchPatientRounds(patientId!), enabled, staleTime: 20_000 }),
    vitalTrends: useQuery({ queryKey: ['patient', patientId, 'vital-trends'], queryFn: () => fetchVitalTrends(patientId!), enabled, staleTime: 20_000 }),
    labTrends: useQuery({ queryKey: ['patient', patientId, 'lab-trends'], queryFn: () => fetchLabTrends(patientId!), enabled, staleTime: 20_000 }),
    clinicalNote: useQuery({ queryKey: ['patient', patientId, 'clinical-note'], queryFn: () => fetchClinicalNote(patientId!), enabled, staleTime: 60_000 }),
    nursingRecords: useQuery({ queryKey: ['patient', patientId, 'nursing'], queryFn: () => fetchNursingRecords(patientId!), enabled, staleTime: 30_000 }),
    evidenceGraph: useQuery({ queryKey: ['patient', patientId, 'evidence-graph'], queryFn: () => fetchPatientEvidenceGraph(patientId!), enabled, staleTime: 30_000 }),
  };
}

export function usePatientEvidenceGraph(patientId?: string) {
  return useQuery({ queryKey: ['patient', patientId, 'evidence-graph'], queryFn: () => fetchPatientEvidenceGraph(patientId!), enabled: Boolean(patientId), staleTime: 30_000 });
}
