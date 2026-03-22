import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

export const markdownComponents = {
  h1: ({ children }: any) => <h1 className="text-4xl font-semibold tracking-[-0.04em] text-stone-50">{children}</h1>,
  h2: ({ children }: any) => <h2 className="text-3xl font-semibold tracking-[-0.03em] text-stone-50">{children}</h2>,
  h3: ({ children }: any) => <h3 className="text-2xl font-semibold tracking-[-0.02em] text-stone-100">{children}</h3>,
  h4: ({ children }: any) => <h4 className="text-xl font-semibold text-stone-100">{children}</h4>,
  h5: ({ children }: any) => <h5 className="text-lg font-medium text-stone-100">{children}</h5>,
  h6: ({ children }: any) => <h6 className="text-base font-medium uppercase tracking-[0.12em] text-stone-400">{children}</h6>,
  p: ({ children }: any) => <p className="text-[15px] leading-7 text-stone-200">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc space-y-2 pl-6 text-[15px] leading-7 text-stone-200">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal space-y-2 pl-6 text-[15px] leading-7 text-stone-200">{children}</ol>,
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-2 border-amber-300/50 pl-4 italic text-stone-400">{children}</blockquote>
  ),
  pre: ({ children }: any) => (
    <pre className="overflow-x-auto rounded-2xl border border-stone-800 bg-stone-950/90 px-4 py-3 text-sm text-stone-200">
      {children}
    </pre>
  ),
  details: ({ children }: any) => (
    <details className="group rounded-2xl border border-stone-800/90 bg-stone-950/60 px-4 py-3 text-stone-200">
      {children}
    </details>
  ),
  summary: ({ children }: any) => (
    <summary className="cursor-pointer list-none text-sm font-medium text-stone-100 marker:hidden transition-colors group-open:text-amber-200">
      <span className="inline-flex items-center gap-2">
        <span className="text-stone-500 transition-transform duration-200 group-open:rotate-90">›</span>
        {children}
      </span>
    </summary>
  ),
  hr: () => <hr className="border-0 border-t border-stone-800/80" />,
  a: ({ href, children }: any) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-medium text-amber-300 underline decoration-amber-300/40 underline-offset-4 transition-colors hover:text-amber-200"
    >
      {children}
    </a>
  ),
  code: ({ className, inline, children, ...props }: any) => (
    <code
      className={cn(
        "font-mono text-[0.9em]",
        inline && "rounded-md bg-stone-900 px-1.5 py-0.5 text-stone-100",
        className,
      )}
      {...props}
    >
      {children}
    </code>
  ),
};

export function MarkdownPreview({ markdown }: { markdown: string }) {
  if (!markdown.trim()) {
    return <p className="text-sm text-stone-500">Nothing to preview yet.</p>;
  }

  return (
    <div className="space-y-4">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

export function MarkdownLine({
  markdown,
  placeholder = "Click to edit this line.",
}: {
  markdown: string;
  placeholder?: string;
}) {
  if (!markdown.trim()) {
    return <span className="text-sm text-stone-500/80">{placeholder}</span>;
  }

  return (
    <div className="space-y-3">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
