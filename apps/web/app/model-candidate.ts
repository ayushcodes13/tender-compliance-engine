const modelFields=new Set([
  'page','quote','category','row_type','remark','display_lines',
  'heading_prefix','merge_with_next','continues_previous',
]);

/** Model data cannot assert parser-owned geometry, cell identity, or transcription status. */
export function modelCandidateFields<T extends object>(value:T):Partial<T> {
  if(!value||typeof value!=='object'||Array.isArray(value))return {};
  return Object.fromEntries(Object.entries(value).filter(([key])=>modelFields.has(key))) as Partial<T>;
}
