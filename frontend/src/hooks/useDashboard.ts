import { useCallback, useEffect, useState } from "react";
import { getDashboardOverview } from "../api/dashboard";
import type { DashboardOverview } from "../types/dashboard";
export function useDashboard() {
  const [data,setData]=useState<DashboardOverview|null>(null); const [loading,setLoading]=useState(true); const [error,setError]=useState<string|null>(null);
  const load=useCallback(async()=>{ setLoading(true); setError(null); try{setData(await getDashboardOverview())}catch{setError("The live dashboard could not be loaded. Check that the RecoverIQ API and database are running.")}finally{setLoading(false)} },[]);
  useEffect(()=>{void load()},[load]); return {data,loading,error,retry:load};
}
