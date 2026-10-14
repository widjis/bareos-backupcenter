"use client";
import { useRef, useState, isValidElement } from "react";
import {
  Search,
  X,
  ArrowDownUp,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
export function SearchField({
  value,
  onChange,
  label = "Search this view",
  onComposition,
}: {
  value: string;
  onChange: (v: string) => void;
  label?: string;
  onComposition?: (v: boolean) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="search-field">
      <Search size={16} aria-hidden="true" />
      <input
        ref={input}
        aria-label={label}
        placeholder="Search this view…"
        value={value}
        onCompositionStart={() => onComposition?.(true)}
        onCompositionEnd={() => onComposition?.(false)}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button
          aria-label="Clear search"
          onClick={() => {
            onChange("");
            input.current?.focus();
          }}
        >
          <X size={15} />
        </button>
      )}
    </div>
  );
}
function cellText(cell: React.ReactNode): string {
  if (typeof cell === "string" || typeof cell === "number") return String(cell);
  if (Array.isArray(cell)) return cell.map(cellText).join(" ");
  if (isValidElement<{ children?: React.ReactNode; value?: string }>(cell)) {
    return cell.props.value || cellText(cell.props.children);
  }
  return "";
}
export function DataTable({
  headers,
  rows,
  page,
  setPage,
  empty,
  server,
}: {
  headers: string[];
  rows: React.ReactNode[][];
  page: number;
  setPage: (p: number) => void;
  empty: string;
  server?: {
    total: number;
    size: number;
    descending: boolean;
    sort: () => void;
  };
}) {
  const [sortDirection, setSortDirection] = useState<
    "ascending" | "descending" | null
  >(null);
  const ordered =
    !server && sortDirection
      ? [...rows].sort(
          (a, b) =>
            cellText(a[0]).localeCompare(cellText(b[0]), "en", {
              numeric: true,
            }) * (sortDirection === "ascending" ? 1 : -1),
        )
      : rows;
  const size = server?.size || 8;
  const total = server?.total ?? rows.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const safe = Math.min(page, pages);
  return (
    <div className="table-panel">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  aria-sort={
                    i === 0
                      ? server
                        ? server.descending
                          ? "descending"
                          : "ascending"
                        : sortDirection || "none"
                      : undefined
                  }
                >
                  {i === 0 ? (
                    <button
                      className="sort-button"
                      onClick={() => {
                        if (server) {
                          server.sort();
                          return;
                        }
                        setSortDirection(
                          sortDirection === "ascending"
                            ? "descending"
                            : "ascending",
                        );
                        setPage(1);
                      }}
                    >
                      {h}
                      <ArrowDownUp size={12} aria-hidden="true" />
                    </button>
                  ) : (
                    h
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(server
              ? ordered
              : ordered.slice((safe - 1) * size, safe * size)
            ).map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <div className="empty">
            <Search size={25} />
            <strong>{empty}</strong>
            <span>Try a different search or refresh the connection.</span>
          </div>
        )}
      </div>
      <div className="pagination">
        <span>
          {total
            ? `${(safe - 1) * size + 1}–${Math.min(safe * size, total)} of ${total}`
            : "0 results"}
        </span>
        <div>
          <button
            aria-label="Previous page"
            disabled={safe === 1}
            onClick={() => setPage(safe - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <span>
            Page {safe} of {pages}
          </span>
          <button
            aria-label="Next page"
            disabled={safe === pages}
            onClick={() => setPage(safe + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
