import { configureStore } from "@reduxjs/toolkit";
import { setupListeners } from "@reduxjs/toolkit/query";
import { todosApi } from "./todosApi.js";

export const store = configureStore({
  reducer: {
    [todosApi.reducerPath]: todosApi.reducer,
  },
  middleware: (getDefault) => getDefault().concat(todosApi.middleware),
});

setupListeners(store.dispatch);
