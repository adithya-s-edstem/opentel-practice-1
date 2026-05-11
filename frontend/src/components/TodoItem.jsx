import { useState } from "react";
import TodoForm from "./TodoForm.jsx";
import {
  useUpdateTodoMutation,
  useCompleteTodoMutation,
  useDeleteTodoMutation,
} from "../store/todosApi.js";

function formatDue(iso) {
  if (!iso) return "No due date";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TodoItem({ todo }) {
  const [editing, setEditing] = useState(false);
  const [updateTodo, { isLoading: saving }] = useUpdateTodoMutation();
  const [completeTodo] = useCompleteTodoMutation();
  const [deleteTodo] = useDeleteTodoMutation();

  const toggle = () => completeTodo(todo.id);

  const save = async (patch) => {
    await updateTodo({ id: todo.id, ...patch });
    setEditing(false);
  };

  if (editing) {
    return (
      <TodoForm
        initial={todo}
        onSubmit={save}
        onCancel={() => setEditing(false)}
        submitting={saving}
      />
    );
  }

  return (
    <div className="flex items-start gap-3 bg-white rounded-xl shadow-sm ring-1 ring-slate-200 p-4 hover:ring-indigo-200 transition">
      <button
        onClick={toggle}
        aria-label={todo.completed ? "Mark incomplete" : "Mark done"}
        className={`mt-1 h-5 w-5 shrink-0 rounded-md border-2 transition flex items-center justify-center ${
          todo.completed
            ? "bg-indigo-600 border-indigo-600 text-white"
            : "border-slate-300 hover:border-indigo-500"
        }`}
      >
        {todo.completed && (
          <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3">
            <path d="M3 8l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </button>

      <div className="flex-1 min-w-0">
        <p
          className={`font-medium text-slate-900 break-words ${
            todo.completed ? "line-through text-slate-400" : ""
          }`}
        >
          {todo.title}
        </p>
        {todo.description && (
          <p
            className={`text-sm mt-0.5 break-words ${
              todo.completed ? "text-slate-300 line-through" : "text-slate-500"
            }`}
          >
            {todo.description}
          </p>
        )}
        <p className="mt-1 text-xs text-slate-400">{formatDue(todo.due_date)}</p>
      </div>

      <div className="flex gap-1">
        <button
          onClick={() => setEditing(true)}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          aria-label="Edit"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
            <path d="M13.586 3.586a2 2 0 112.828 2.828l-9.5 9.5a2 2 0 01-.879.515l-3 .857a.5.5 0 01-.618-.618l.857-3a2 2 0 01.515-.879l9.5-9.5z" />
          </svg>
        </button>
        <button
          onClick={() => deleteTodo(todo.id)}
          className="rounded-md p-2 text-slate-500 hover:bg-red-50 hover:text-red-600"
          aria-label="Delete"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor">
            <path d="M6 2a1 1 0 011-1h6a1 1 0 011 1v1h3a1 1 0 110 2h-1v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5H3a1 1 0 110-2h3V2zm2 5a1 1 0 012 0v8a1 1 0 11-2 0V7zm4 0a1 1 0 112 0v8a1 1 0 11-2 0V7z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
