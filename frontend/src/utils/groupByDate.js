const GROUP_ORDER = [
  "Overdue",
  "Today",
  "Tomorrow",
  "This Week",
  "Next Week",
  "This Month",
  "Next Month",
  "Later",
  "No Date",
];

const startOfDay = (d) => {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
};

const addDays = (d, n) => {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
};

// Week starts Monday; end is exclusive (next Monday 00:00).
const startOfWeek = (d) => {
  const x = startOfDay(d);
  const day = x.getDay(); // 0=Sun..6=Sat
  const diff = (day + 6) % 7; // days since Monday
  return addDays(x, -diff);
};

const startOfMonth = (d) => {
  const x = startOfDay(d);
  x.setDate(1);
  return x;
};

const addMonths = (d, n) => {
  const x = new Date(d);
  x.setMonth(x.getMonth() + n);
  return x;
};

export function bucketFor(dueIso, now = new Date()) {
  if (!dueIso) return "No Date";
  const due = startOfDay(new Date(dueIso));
  const today = startOfDay(now);

  if (due < today) return "Overdue";
  if (due.getTime() === today.getTime()) return "Today";
  if (due.getTime() === addDays(today, 1).getTime()) return "Tomorrow";

  const weekStart = startOfWeek(today);
  const nextWeekStart = addDays(weekStart, 7);
  const weekAfterNext = addDays(weekStart, 14);
  if (due < nextWeekStart) return "This Week";
  if (due < weekAfterNext) return "Next Week";

  const monthStart = startOfMonth(today);
  const nextMonthStart = addMonths(monthStart, 1);
  const monthAfterNext = addMonths(monthStart, 2);
  if (due < nextMonthStart) return "This Month";
  if (due < monthAfterNext) return "Next Month";

  return "Later";
}

export function groupTodos(todos, now = new Date()) {
  const sorted = [...todos].sort((a, b) => {
    if (!a.due_date && !b.due_date) return a.id - b.id;
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return new Date(a.due_date) - new Date(b.due_date);
  });

  const buckets = new Map();
  for (const todo of sorted) {
    const key = bucketFor(todo.due_date, now);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(todo);
  }

  return GROUP_ORDER.filter((g) => buckets.has(g)).map((label) => ({
    label,
    items: buckets.get(label),
  }));
}
