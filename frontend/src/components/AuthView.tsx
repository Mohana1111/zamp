import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import {
  Lock,
  User as UserIcon,
  Mail,
  ArrowRight,
  Eye,
  EyeOff,
  AlertCircle,
  ShieldCheck
} from 'lucide-react';

export const AuthView: React.FC = () => {
  const { login, signup, error, clearError } = useAuth();
  const [mode, setMode] = useState<'LOGIN' | 'SIGNUP'>('LOGIN');

  // Form State
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Local validation & submission state
  const [localError, setLocalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleModeSwitch = (newMode: 'LOGIN' | 'SIGNUP') => {
    setMode(newMode);
    setLocalError(null);
    clearError();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    const cleanUsername = username.trim();
    if (!cleanUsername) {
      setLocalError('Please enter your username.');
      return;
    }

    if (!password) {
      setLocalError('Please enter your password.');
      return;
    }

    if (mode === 'SIGNUP') {
      if (cleanUsername.length < 3) {
        setLocalError('Username must be at least 3 characters long.');
        return;
      }
      if (password.length < 6) {
        setLocalError('Password must be at least 6 characters long.');
        return;
      }
      if (password !== confirmPassword) {
        setLocalError('Passwords do not match. Please re-enter.');
        return;
      }
    }

    setIsSubmitting(true);
    try {
      if (mode === 'LOGIN') {
        await login({ username: cleanUsername, password });
      } else {
        await signup({
          username: cleanUsername,
          password,
          name: fullName.trim() || cleanUsername,
          email: email.trim() || `${cleanUsername}@company.com`
        });
      }
    } catch {
      // Handled by context / error state
    } finally {
      setIsSubmitting(false);
    }
  };

  const displayError = localError || error;

  return (
    <div className="min-h-screen bg-neutral-50/60 flex flex-col justify-center items-center px-4 sm:px-6 py-12 font-sans selection:bg-neutral-900 selection:text-white">
      {/* Top Brand Logo */}
      <div className="w-full max-w-sm mb-6 text-center space-y-3">
        <div className="inline-flex items-center justify-center p-3 rounded-2xl bg-white border border-neutral-200/80 shadow-xs">
          <svg
            width="32"
            height="26"
            viewBox="0 0 28 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="text-neutral-900"
          >
            <polygon points="6,2 26,2 21,10 1,10" fill="currentColor" />
            <polygon points="5,13 25,13 20,21 0,21" fill="currentColor" />
          </svg>
        </div>

        <div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            zamp
          </h1>
          <p className="mt-1 text-xs text-neutral-500">
            Accounts Payable Verification & Decisioning
          </p>
        </div>
      </div>

      {/* Main Auth Card */}
      <div className="w-full max-w-sm bg-white border border-neutral-200/90 rounded-2xl shadow-sm p-6 space-y-5">
        {/* Tab Toggle: Sign In vs Sign Up */}
        <div className="grid grid-cols-2 p-1 rounded-xl bg-neutral-100 border border-neutral-200 text-xs font-medium">
          <button
            type="button"
            onClick={() => handleModeSwitch('LOGIN')}
            className={`py-1.5 rounded-lg transition-all cursor-pointer ${
              mode === 'LOGIN'
                ? 'bg-white text-neutral-900 shadow-xs font-semibold'
                : 'text-neutral-500 hover:text-neutral-900'
            }`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => handleModeSwitch('SIGNUP')}
            className={`py-1.5 rounded-lg transition-all cursor-pointer ${
              mode === 'SIGNUP'
                ? 'bg-white text-neutral-900 shadow-xs font-semibold'
                : 'text-neutral-500 hover:text-neutral-900'
            }`}
          >
            Create account
          </button>
        </div>

        {/* Error Alert Banner */}
        {displayError && (
          <div className="flex items-start gap-2.5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 animate-in fade-in duration-150">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div className="flex-1 font-medium">{displayError}</div>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Username */}
          <div className="space-y-1">
            <label className="block text-xs font-medium text-neutral-700">
              Username
            </label>
            <div className="relative">
              <UserIcon className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin_1"
                autoComplete="username"
                className="w-full rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-xs text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
              />
            </div>
          </div>

          {/* Sign Up extra fields */}
          {mode === 'SIGNUP' && (
            <>
              <div className="space-y-1">
                <label className="block text-xs font-medium text-neutral-700">
                  Full Name
                </label>
                <div className="relative">
                  <UserIcon className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Sarah Jenkins"
                    className="w-full rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-xs text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-neutral-700">
                  Email
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="sarah@company.com"
                    autoComplete="email"
                    className="w-full rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-xs text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
                  />
                </div>
              </div>
            </>
          )}

          {/* Password */}
          <div className="space-y-1">
            <label className="block text-xs font-medium text-neutral-700">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                autoComplete={mode === 'LOGIN' ? 'current-password' : 'new-password'}
                className="w-full rounded-xl border border-neutral-200 bg-white pl-9 pr-9 py-2 text-xs text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors font-mono"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-neutral-400 hover:text-neutral-900 cursor-pointer"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Confirm Password */}
          {mode === 'SIGNUP' && (
            <div className="space-y-1">
              <label className="block text-xs font-medium text-neutral-700">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  autoComplete="new-password"
                  className="w-full rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-xs text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors font-mono"
                />
              </div>
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-2 rounded-xl bg-neutral-900 hover:bg-black text-white py-2.5 px-4 text-xs font-medium transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50"
          >
            <span>{mode === 'LOGIN' ? 'Sign in' : 'Create account'}</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </form>

        <div className="pt-3 border-t border-neutral-100 flex items-center justify-center gap-1.5 text-[11px] text-neutral-400">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
          <span>Encrypted corporate session</span>
        </div>
      </div>
    </div>
  );
};
