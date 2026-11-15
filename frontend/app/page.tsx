import Link from "next/link";
import { Suspense } from "react";

import { API_BASE as API_URL } from "./lib";
import NotificationBell from "./NotificationBell";

const PAGE_SIZE = 30;

const CATEGORIES = [
  { key: "", label: "All" },
  { key: "news", label: "News" },
  { key: "government", label: "Government" },
  { key: "regulator", label: "Regulators" },
];

type Article = {
  id: number;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  source: { id: number; name: string; category: string };
  cluster_id?: string | null;
  also_covered_by?: number;
};

type ArticlePage = { items: Article[]; has_more: boolean };

const timeFormat = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

async function loadArticles(
  category: string,
  q: string,
  offset: number,
  group: boolean
): Promise<ArticlePage | null> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  if (group) params.set("group", "true");
  try {
    const response = await fetch(`${API_URL}/api/articles?${params}`, { cache: "no-store" });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

function pageHref(category: string, q: string, offset: number, group: boolean): string {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  if (group) params.set("group", "true");
  if (offset > 0) params.set("offset", String(offset));
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default function Home({ searchParams }: { searchParams: SearchParams }) {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Market Intel</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Indian market, economy and policy news in one place. Times are in IST.
          </p>
        </div>
        <NotificationBell />
      </header>
      <Suspense fallback={<p className="py-12 text-center text-sm text-zinc-500">Loading…</p>}>
        <Feed searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Feed({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const category = first(sp.category);
  const q = first(sp.q).trim();
  const offset = Math.max(0, Number.parseInt(first(sp.offset), 10) || 0);
  const group = first(sp.group) === "true";
  const page = await loadArticles(category, q, offset, group);

  return (
    <>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <nav className="flex flex-wrap gap-2">
            {CATEGORIES.map((c) => (
              <Link
                key={c.key}
                href={pageHref(c.key, q, 0, group)}
                className={`rounded-full border px-3 py-1 text-sm ${
                  c.key === category
                    ? "border-foreground bg-foreground text-background"
                    : "border-zinc-300 hover:border-zinc-500 dark:border-zinc-700"
                }`}
              >
                {c.label}
              </Link>
            ))}
          </nav>
          <Link
            href={pageHref(category, q, 0, !group)}
            className={`rounded-full border px-3 py-1 text-sm transition-colors ${
              group
                ? "border-emerald-600 bg-emerald-50 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-950/40 dark:text-emerald-300"
                : "border-zinc-300 text-zinc-600 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-400"
            }`}
            title="Group identical stories across sources"
          >
            {group ? "✓ Grouped" : "Group"}
          </Link>
        </div>
        <form action="/" className="flex gap-2">
          {category && <input type="hidden" name="category" value={category} />}
          {group && <input type="hidden" name="group" value="true" />}
          <input
            name="q"
            defaultValue={q}
            maxLength={100}
            placeholder="Search headlines"
            className="w-full rounded-md border border-zinc-300 bg-transparent px-3 py-1.5 text-sm sm:w-56 dark:border-zinc-700"
          />
          <button className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:border-zinc-500 dark:border-zinc-700">
            Search
          </button>
        </form>
      </div>

      {page === null ? (
        <p className="rounded-md border border-red-300 p-4 text-sm text-red-700 dark:border-red-800 dark:text-red-400">
          The news service is not reachable right now. Please try again shortly.
        </p>
      ) : page.items.length === 0 ? (
        <p className="py-12 text-center text-sm text-zinc-500">No articles match.</p>
      ) : (
        <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {page.items.map((a) => (
            <li key={a.id} className="py-4">
              <div className="mb-1 flex flex-wrap items-center gap-x-2 text-xs text-zinc-500">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">{a.source.name}</span>
                <span>·</span>
                <time dateTime={a.published_at}>{timeFormat.format(new Date(a.published_at))}</time>
                {a.also_covered_by && a.also_covered_by > 0 ? (
                  <>
                    <span>·</span>
                    <span className="inline-flex items-center rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      +{a.also_covered_by} more {a.also_covered_by === 1 ? "source" : "sources"}
                    </span>
                  </>
                ) : null}
              </div>
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                title={a.title}
                className="line-clamp-3 font-medium leading-snug hover:underline"
              >
                {a.title}
              </a>
              {a.summary && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{a.summary}</p>}
            </li>
          ))}
        </ul>
      )}

      {page && (offset > 0 || page.has_more) && (
        <div className="mt-6 flex justify-between text-sm">
          {offset > 0 ? (
            <Link
              href={pageHref(category, q, Math.max(0, offset - PAGE_SIZE), group)}
              className="hover:underline"
            >
              ← Newer
            </Link>
          ) : (
            <span />
          )}
          {page.has_more && (
            <Link href={pageHref(category, q, offset + PAGE_SIZE, group)} className="hover:underline">
              Older →
            </Link>
          )}
        </div>
      )}
    </>
  );
}
