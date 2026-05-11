import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export const todosApi = createApi({
  reducerPath: "todosApi",
  baseQuery: fetchBaseQuery({ baseUrl: "/api" }),
  tagTypes: ["Todo"],
  endpoints: (builder) => ({
    getTodos: builder.query({
      query: () => "/todos",
      providesTags: (result) =>
        result
          ? [
              ...result.map((t) => ({ type: "Todo", id: t.id })),
              { type: "Todo", id: "LIST" },
            ]
          : [{ type: "Todo", id: "LIST" }],
    }),
    addTodo: builder.mutation({
      query: (body) => ({ url: "/todos", method: "POST", body }),
      invalidatesTags: [{ type: "Todo", id: "LIST" }],
    }),
    updateTodo: builder.mutation({
      query: ({ id, ...patch }) => ({
        url: `/todos/${id}`,
        method: "PUT",
        body: patch,
      }),
      invalidatesTags: (_r, _e, { id }) => [
        { type: "Todo", id },
        { type: "Todo", id: "LIST" },
      ],
    }),
    completeTodo: builder.mutation({
      query: (id) => ({ url: `/todos/${id}/complete`, method: "POST" }),
      invalidatesTags: (_r, _e, id) => [
        { type: "Todo", id },
        { type: "Todo", id: "LIST" },
      ],
    }),
    deleteTodo: builder.mutation({
      query: (id) => ({ url: `/todos/${id}`, method: "DELETE" }),
      invalidatesTags: (_r, _e, id) => [
        { type: "Todo", id },
        { type: "Todo", id: "LIST" },
      ],
    }),
  }),
});

export const {
  useGetTodosQuery,
  useAddTodoMutation,
  useUpdateTodoMutation,
  useCompleteTodoMutation,
  useDeleteTodoMutation,
} = todosApi;
