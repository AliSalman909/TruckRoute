import axios, { AxiosError } from 'axios';
import type { ApiErrorBody } from '../types';

export const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`,
  timeout: 90_000,
  headers: { 'Content-Type': 'application/json' },
});

export interface ApiError {
  code: string;
  message: string;
  fieldErrors: Record<string, string>;
}

/** Normalise axios/network/API errors into one shape the UI can render. */
export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const e = err as AxiosError<ApiErrorBody>;
    const body = e.response?.data;
    if (body?.status === 'ERROR') {
      const fieldErrors: Record<string, string> = {};
      for (const [field, value] of Object.entries(body.error.details ?? {})) {
        fieldErrors[field] = Array.isArray(value) ? String(value[0]) : String(value);
      }
      const firstField = Object.values(fieldErrors)[0];
      const message =
        body.error.code === 'VALIDATION_ERROR' && firstField ? firstField : body.error.message;
      return { code: body.error.code, message, fieldErrors };
    }
    if (e.code === 'ECONNABORTED') {
      return { code: 'TIMEOUT', message: 'The analysis took too long. Please try again.', fieldErrors: {} };
    }
    if (!e.response) {
      return {
        code: 'NETWORK',
        message: 'Cannot reach the SafeHaul API. Is the Django server running on port 8000?',
        fieldErrors: {},
      };
    }
    return { code: `HTTP_${e.response.status}`, message: `Server error (${e.response.status}).`, fieldErrors: {} };
  }
  return { code: 'UNKNOWN', message: 'Something went wrong.', fieldErrors: {} };
}
