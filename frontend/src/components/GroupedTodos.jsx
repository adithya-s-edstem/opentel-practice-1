import { useMemo } from "react";
import { groupTodos } from "../utils/groupByDate.js";
import TodoItem from "./TodoItem.jsx";

const TONE = {
  Overdue: "bg-red-50 text-red-700 ring-red-200",
  Today: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  Tomorrow: "bg-sky-50 text-sky-700 ring-sky-200",
  "This Week": "bg-emerald-50 text-emerald-700 ring-emerald-200",
  "Next Week": "bg-teal-50 text-teal-700 ring-teal-200",
  "This Month": "bg-amber-50 text-amber-700 ring-amber-200",
  "Next Month": "bg-orange-50 text-orange-700 ring-orange-200",
  Later: "bg-slate-100 text-slate-700 ring-slate-200",
  "No Date": "bg-slate-100 text-slate-500 ring-slate-200",
};

export default function GroupedTodos({ todos }) {
  const groups = useMemo(() => groupTodos(todos), [todos]);

  if (!groups.length) {
    return (
      <div className="text-center text-slate-500 py-12">
        Nothing here yet — add your first todo above.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {groups.map(({ label, items }) => (
        <section key={label}>
          <div className="flex items-center gap-3 mb-3">
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                TONE[label] || TONE["Later"]
              }`}
            >
              {label}
            </span>
            <span className="text-xs text-slate-400">
              {items.length} {items.length === 1 ? "item" : "items"}
            </span>
          </div>
          <div className="space-y-2">
            {items.map((todo) => (
              <TodoItem key={todo.id} todo={todo} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
