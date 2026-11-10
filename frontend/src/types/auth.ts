export interface User {
  id: string;
  username: string;
  name: string;
  role: 'admin' | 'user';
  email?: string;
  created_at?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
  message?: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface SignupCredentials {
  username: string;
  password: string;
  name?: string;
  email?: string;
}
