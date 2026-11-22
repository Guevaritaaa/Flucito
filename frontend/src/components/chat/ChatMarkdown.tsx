import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renderiza solo Markdown; el HTML no se interpreta y los enlaces usan el filtro de URL de react-markdown. */
export function ChatMarkdown({ contenido }: { contenido: string }) {
  return (
    <div className="space-y-3 break-words text-sm leading-relaxed sm:text-[15px] [&_p]:whitespace-pre-wrap [&_strong]:font-semibold [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5 [&_li]:my-1 [&_a]:break-all [&_a]:text-blue-700 [&_a]:underline dark:[&_a]:text-sky-300 [&_code]:break-words [&_code]:rounded [&_code]:bg-slate-900/5 [&_code]:px-1 dark:[&_code]:bg-white/10">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          table: ({ children }) => <div className="max-w-full overflow-x-auto rounded-lg border border-slate-900/10 dark:border-sky-200/20"><table className="w-full border-collapse text-left text-xs sm:text-sm">{children}</table></div>,
          th: ({ children }) => <th scope="col" className="whitespace-nowrap border-b border-slate-900/10 bg-slate-900/5 px-3 py-2 font-semibold dark:border-sky-200/20 dark:bg-white/5">{children}</th>,
          td: ({ children }) => <td className="border-b border-slate-900/10 px-3 py-2 align-top last:pr-4 dark:border-sky-200/10">{children}</td>,
          a: ({ href, children }) => href && /^(https?:|mailto:|\/)/i.test(href) && !href.startsWith("//") ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <>{children}</>,
        }}
      >{contenido}</ReactMarkdown>
    </div>
  );
}
