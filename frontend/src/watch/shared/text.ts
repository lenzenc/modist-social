/** A stage direction as a sentence: some already begin with the person's name, some don't. */
export function actionText(text: string, short: string | undefined): string {
  if (!short || text.toLowerCase().startsWith(short.toLowerCase())) return text;
  return `${short} ${text}`;
}
