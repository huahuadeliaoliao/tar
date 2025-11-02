import { createMarkdownExit } from 'markdown-exit'

type MarkdownEnv = Record<string, unknown>

const md = createMarkdownExit({
  breaks: true,
  linkify: true,
})

const defaultLinkOpen = md.renderer.rules.link_open

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]!
  const targetIndex = token.attrIndex('target')

  if (targetIndex < 0) {
    token.attrPush(['target', '_blank'])
  } else {
    token.attrs?.splice(targetIndex, 1, ['target', '_blank'])
  }

  const relIndex = token.attrIndex('rel')
  const relValue = 'noopener noreferrer'

  if (relIndex < 0) {
    token.attrPush(['rel', relValue])
  } else {
    token.attrs?.splice(relIndex, 1, ['rel', relValue])
  }

  if (defaultLinkOpen) {
    return defaultLinkOpen(tokens, idx, options, env, self)
  }

  return self.renderToken(tokens, idx, options)
}

export function renderMarkdown(content: string, env?: MarkdownEnv): string {
  return md.render(content, env)
}
