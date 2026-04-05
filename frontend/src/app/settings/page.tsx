"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  User,
  Save,
  Loader2,
  Trash2,
  RefreshCw,
} from "lucide-react";
import {
  getResumeStatus,
  uploadResume,
  getUserProfile,
  saveUserProfile,
} from "@/lib/api";
import type { ResumeStatus, UserProfile } from "@/types";

// ───── helpers ─────
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

// ───── blank profile ─────
const EMPTY_PROFILE: UserProfile = {
  full_name: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  linkedin_url: "",
  github_url: "",
};

export default function SettingsPage() {
  // ── resume state ──
  const [resumeStatus, setResumeStatus] = useState<ResumeStatus | null>(null);
  const [resumeLoading, setResumeLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── profile state ──
  const [profile, setProfile] = useState<UserProfile>(EMPTY_PROFILE);
  const [profileLoading, setProfileLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // ── load on mount ──
  useEffect(() => {
    getResumeStatus()
      .then((s) => setResumeStatus(s))
      .catch(() => setResumeStatus({ uploaded: false }))
      .finally(() => setResumeLoading(false));

    getUserProfile()
      .then((p) => {
        if (p) setProfile(p);
      })
      .catch(() => {})
      .finally(() => setProfileLoading(false));
  }, []);

  // ── upload handler ──
  const handleFileUpload = useCallback(
    async (file: File) => {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext !== "pdf" && ext !== "docx") {
        setUploadMsg({ ok: false, text: "Only .pdf and .docx files are accepted." });
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setUploadMsg({ ok: false, text: "File too large. Maximum size is 10 MB." });
        return;
      }

      setUploading(true);
      setUploadMsg(null);
      try {
        const result = await uploadResume(file);
        setResumeStatus(result);
        setUploadMsg({ ok: true, text: `Resume uploaded successfully — ${file.name}` });
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || "Upload failed";
        setUploadMsg({ ok: false, text: msg });
      } finally {
        setUploading(false);
      }
    },
    [],
  );

  // ── drag handlers ──
  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) handleFileUpload(file);
    },
    [handleFileUpload],
  );

  // ── profile save ──
  const handleSaveProfile = async () => {
    setSaving(true);
    setProfileMsg(null);
    try {
      await saveUserProfile(profile);
      setProfileMsg({ ok: true, text: "Profile saved." });
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Save failed";
      setProfileMsg({ ok: false, text: msg });
    } finally {
      setSaving(false);
    }
  };

  const updateField = (field: keyof UserProfile, value: string) =>
    setProfile((prev) => ({ ...prev, [field]: value }));

  // ───── render ─────
  return (
    <div className="space-y-6">
      {/* ─── RESUME SECTION ─── */}
      <section className="panel overflow-hidden">
        <div className="flex items-center gap-3 border-b border-white/10 px-6 py-4">
          <span className="rounded-xl bg-sky-500/10 p-2 dark:bg-sky-500/15">
            <FileText className="h-5 w-5 text-sky-500" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
              Resume
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Upload your resume so the pipeline can match and tailor it per job.
            </p>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {/* Current resume pill */}
          {resumeLoading ? (
            <div className="animate-pulse h-14 rounded-2xl bg-slate-100 dark:bg-slate-800" />
          ) : resumeStatus?.uploaded ? (
            <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-emerald-200/60 bg-emerald-50/50 px-5 py-3.5 dark:border-emerald-500/20 dark:bg-emerald-950/20">
              <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                  {resumeStatus.filename}
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {resumeStatus.size_bytes != null && formatBytes(resumeStatus.size_bytes)}
                  {resumeStatus.last_modified && ` · uploaded ${relativeTime(resumeStatus.last_modified)}`}
                </p>
              </div>
              <button
                onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 rounded-lg bg-slate-900/5 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-900/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
              >
                <RefreshCw className="h-3 w-3" /> Replace
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded-2xl border border-amber-200/60 bg-amber-50/50 px-5 py-3.5 dark:border-amber-500/20 dark:bg-amber-950/20">
              <AlertCircle className="h-5 w-5 text-amber-500 shrink-0" />
              <p className="text-sm text-amber-700 dark:text-amber-300">
                No resume uploaded yet. Upload one below to enable the pipeline.
              </p>
            </div>
          )}

          {/* Drop zone */}
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            className={`group relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-all
              ${dragActive
                ? "border-sky-400 bg-sky-50/40 dark:border-sky-500 dark:bg-sky-950/30"
                : "border-slate-300 hover:border-sky-400 dark:border-slate-700 dark:hover:border-sky-600"
              }`}
          >
            {uploading ? (
              <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
            ) : (
              <Upload className={`h-8 w-8 transition-colors ${dragActive ? "text-sky-500" : "text-slate-400 group-hover:text-sky-500 dark:text-slate-600"}`} />
            )}
            <div>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                {uploading ? "Uploading…" : "Drag & drop your resume here"}
              </p>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                or click to browse · PDF / DOCX · max 10 MB
              </p>
            </div>

            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileUpload(file);
                e.target.value = "";
              }}
            />
          </div>

          {/* toast */}
          {uploadMsg && (
            <div
              className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${
                uploadMsg.ok
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
                  : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300"
              }`}
            >
              {uploadMsg.ok ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <AlertCircle className="h-4 w-4 shrink-0" />}
              {uploadMsg.text}
            </div>
          )}
        </div>
      </section>

      {/* ─── PROFILE SECTION ─── */}
      <section className="panel overflow-hidden">
        <div className="flex items-center gap-3 border-b border-white/10 px-6 py-4">
          <span className="rounded-xl bg-violet-500/10 p-2 dark:bg-violet-500/15">
            <User className="h-5 w-5 text-violet-500" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
              Personal Profile
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Used by the application agent to fill out job forms on your behalf.
            </p>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {profileLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse h-11 rounded-xl bg-slate-100 dark:bg-slate-800" />
              ))}
            </div>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Full Name" value={profile.full_name} onChange={(v) => updateField("full_name", v)} placeholder="Apoorv Nath Tripathi" />
                <Field label="Email" value={profile.email} onChange={(v) => updateField("email", v)} placeholder="you@email.com" type="email" />
                <Field label="First Name" value={profile.first_name} onChange={(v) => updateField("first_name", v)} placeholder="Apoorv" />
                <Field label="Last Name" value={profile.last_name} onChange={(v) => updateField("last_name", v)} placeholder="Tripathi" />
                <Field label="Phone" value={profile.phone} onChange={(v) => updateField("phone", v)} placeholder="+91 92051 02348" type="tel" />
                <Field label="LinkedIn URL" value={profile.linkedin_url} onChange={(v) => updateField("linkedin_url", v)} placeholder="https://linkedin.com/in/…" type="url" />
                <Field label="GitHub URL (optional)" value={profile.github_url || ""} onChange={(v) => updateField("github_url", v)} placeholder="https://github.com/…" type="url" />
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={handleSaveProfile}
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-sky-600 dark:hover:bg-sky-500"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {saving ? "Saving…" : "Save Profile"}
                </button>

                {profileMsg && (
                  <span
                    className={`text-sm ${
                      profileMsg.ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
                    }`}
                  >
                    {profileMsg.ok ? "✓" : "✕"} {profileMsg.text}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

// ── reusable field ──
function Field({
  label,
  value,
  onChange,
  placeholder = "",
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-400">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20 dark:border-slate-700 dark:bg-slate-800/50 dark:text-white dark:placeholder:text-slate-500 dark:focus:border-sky-500"
      />
    </div>
  );
}
