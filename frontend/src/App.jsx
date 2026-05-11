import { useGetTodosQuery, useAddTodoMutation } from "./store/todosApi.js";
import TodoForm from "./components/TodoForm.jsx";
import GroupedTodos from "./components/GroupedTodos.jsx";

export default function App() {
  const { data: todos = [], isLoading, isError, refetch } = useGetTodosQuery();
  const [addTodo, { isLoading: adding }] = useAddTodoMutation();

  return (
    <div className="min-h-screen">
      <div className="max-w-2xl mx-auto px-4 py-10">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight">Todos</h1>
          <p className="text-slate-500 text-sm mt-1">
            Grouped by when they're due.
          </p>
        </header>

        <div className="mb-8">
          <TodoForm onSubmit={(body) => addTodo(body).unwrap()} submitting={adding} />
        </div>

        {isLoading && (
          <div className="text-center text-slate-500 py-12">Loading…</div>
        )}

        {isError && (
          <div className="rounded-lg bg-red-50 ring-1 ring-red-200 p-4 text-sm text-red-700">
            Couldn't reach the API.
            <button
              onClick={refetch}
              className="ml-2 underline font-medium hover:text-red-900"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && <GroupedTodos todos={todos} />}
      </div>
    </div>
  );
}
