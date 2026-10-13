import axios from "axios";

export const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

export async function fetcher<T>(url: string): Promise<T> {
  const res = await api.get<T>(url);
  return res.data;
}
