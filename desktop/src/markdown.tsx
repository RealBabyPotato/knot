import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const markdownComponents = {
  h1: ({ children }: any) => <h1>{children}</h1>,
  h2: ({ children }: any) => <h2>{children}</h2>,
  h3: ({ children }: any) => <h3>{children}</h3>,
  h4: ({ children }: any) => <h4>{children}</h4>,
  h5: ({ children }: any) => <h5>{children}</h5>,
  h6: ({ children }: any) => <h6>{children}</h6>,
  p: ({ children }: any) => <p>{children}</p>,
  ul: ({ children }: any) => <ul>{children}</ul>,
  ol: ({ children }: any) => <ol>{children}</ol>,
  blockquote: ({ children }: any) => <blockquote>{children}</blockquote>,
  pre: ({ children }: any) => <pre>{children}</pre>,
  hr: () => <hr />,
  a: ({ href, children }: any) => (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ),
  code: ({ className, children, ...props }: any) => (
    <code className={className} {...props}>
      {children}
    </code>
  ),
};

export function MarkdownPreview({ markdown }: { markdown: string }) {
  if (!markdown.trim()) {
    return <p style={{ color: "hsl(var(--muted-foreground))" }}>Nothing to preview yet.</p>;
  }

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
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
    return <span style={{ color: "hsl(var(--muted-foreground))", opacity: 0.6 }}>{placeholder}</span>;
  }

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
