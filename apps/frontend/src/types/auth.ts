export interface UserIdentity {
  name: string;
  role: 'doctor' | 'nurse';
  title: string;
  department: string;
  actor_id?: string;
  job_number?: string;
}

export interface LoginResponse {
  name: string;
  role: 'doctor' | 'nurse';
  title: string;
  department: string;
  job_number: string;
  is_manager: boolean;
  token: string;
  default_route: '/admin' | '/workbench' | '/nurse';
}
