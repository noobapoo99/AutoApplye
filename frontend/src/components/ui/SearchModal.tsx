"use client";
import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { triggerJobSearch } from '@/lib/api';
import { Loader2 } from 'lucide-react';

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

export default function SearchModal({ open, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const [maxJobs, setMaxJobs] = useState(5);
  const [strategy, setStrategy] = useState('keyword_injection');
  const [loading, setLoading] = useState(false);
  const [showToast, setShowToast] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await triggerJobSearch(query, maxJobs, strategy);
      setShowToast(true);
      setTimeout(() => setShowToast(false), 2500);
      onClose();
      setQuery('');
      setMaxJobs(5);
      setStrategy('keyword_injection');
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Dialog.Root open={open} onOpenChange={onClose}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-md z-50">
            <Dialog.Title className="text-white text-xl font-semibold mb-6">Find Jobs</Dialog.Title>
            
            <div className="space-y-4">
              <div>
                <label className="block text-zinc-400 text-sm mb-1.5">Role or keywords</label>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. Python backend engineer, data engineer"
                  className="w-full bg-zinc-800 border border-zinc-700 focus:border-blue-500 text-white rounded-lg px-3 py-2.5 text-sm outline-none transition-colors"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="text-zinc-400 text-sm">Max jobs: <span className="text-white font-medium">{maxJobs}</span></label>
                </div>
                <input
                  type="range"
                  min="1"
                  max="10"
                  value={maxJobs}
                  onChange={(e) => setMaxJobs(parseInt(e.target.value))}
                  className="w-full accent-blue-500 mt-1.5"
                />
              </div>

              <div>
                <label className="block text-zinc-400 text-sm mb-1.5">Edit strategy</label>
                <select
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 text-white rounded-lg px-3 py-2.5 text-sm outline-none"
                >
                  <option value="keyword_injection">Keyword Injection (default)</option>
                  <option value="summary_rewrite">Summary Rewrite</option>
                  <option value="skills_reorder">Skills Reorder</option>
                </select>
              </div>
            </div>

            <button
              onClick={handleSubmit}
              disabled={loading}
              className={`w-full mt-6 py-2.5 rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2 ${
                loading ? 'bg-blue-800 text-blue-300 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 text-white'
              }`}
            >
              {loading && <Loader2 className="animate-spin w-4 h-4" />}
              {loading ? 'Starting...' : 'Start Pipeline'}
            </button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {showToast && (
        <div className="fixed bottom-4 right-4 bg-green-900/90 border border-green-700 text-green-300 rounded-xl px-4 py-3 text-sm z-50">
          Pipeline started ✓
        </div>
      )}
    </>
  );
}
