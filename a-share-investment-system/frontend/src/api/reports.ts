import axios from "axios"
import { get, post, del } from "./request"

export const reportsApi = {
  list: (params?: any) => get("/api/reports", params),
  getById: (id: string) => get(`/api/reports/${id}`),
  delete: (id: string) => del(`/api/reports/${id}`),
  download: async (id: string, format?: string) => {
    const res = await axios.get(`/api/reports/${id}/download`, {
      params: { format },
      responseType: "blob",
    })
    return res.data
  },
  getLatestBySymbol: (symbols: string[]) => post("/api/reports/latest-by-symbols", { symbols }),
  sendEmail: (id: string) => post(`/api/reports/${id}/send-email`),
}
