import { motion, AnimatePresence } from "framer-motion";
import { useAgentStore } from "@/store/agentStore";
import { CheckCircle2, XCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

export function StatusBanner() {
  const { task } = useAgentStore();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (task?.status === 'completed' || task?.status === 'failed') {
      setVisible(true);
      const timer = setTimeout(() => setVisible(false), 6000);
      return () => clearTimeout(timer);
    }
    setVisible(false);
  }, [task?.status]);

  if (!visible || !task) return null;

  const isSuccess = task.status === 'completed';

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 8 }}
        transition={{ duration: 0.2 }}
        className={`fixed bottom-20 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl border text-xs font-medium shadow-lg ${
          isSuccess
            ? 'bg-success/10 border-success/30 text-success'
            : 'bg-destructive/10 border-destructive/30 text-destructive'
        }`}
      >
        {isSuccess ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
        {isSuccess
          ? `Task completed in ${task.steps.length} steps`
          : task.error || 'Task failed'
        }
        <button onClick={() => setVisible(false)} className="ml-2 opacity-60 hover:opacity-100">
          <X className="h-3 w-3" />
        </button>
      </motion.div>
    </AnimatePresence>
  );
}
