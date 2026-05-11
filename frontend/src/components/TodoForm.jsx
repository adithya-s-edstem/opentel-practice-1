import { useEffect, useState } from "react";

const blank = { title: "", description: "", due_date: "" };

function toInputValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function TodoForm({ initial, onSubmit, onCancel, submitting }) {
  const [form, setForm] = useState(blank);

  useEffect(() => {
    if (initial) {
      setForm({
        title: initial.title ?? "",
        description: initial.description ?? "",
        due_date: toInputValue(initial.due_date),
      });
    } else {
      setForm(blank);
    }
  }, [initial]);

  const handleChange = (field) => (e) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const title = form.title.trim();
    if (!title) return;
    await onSubmit({
      title,
      description: form.description.trim(),
      due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
    });
    if (!initial) setForm(blank);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white rounded-2xl shadow-sm ring-1 ring-slate-200 p-5 space-y-3"
    >
      <input
        type="text"
        required
        placeholder="What needs doing?"
        value={form.title}
        onChange={handleChange("title")}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <textarea
        placeholder="Notes (optional)"
        value={form.description}
        onChange={handleChange("description")}
        rows={2}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-slate-600">
          Due
          <input
            type="datetime-local"
            value={form.due_date}
            onChange={handleChange("due_date")}
            className="ml-2 rounded-lg border border-slate-200 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </label>
        <div className="ml-auto flex gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {initial ? "Save" : "Add todo"}
          </button>
        </div>
      </div>
    </form>
  );
}
