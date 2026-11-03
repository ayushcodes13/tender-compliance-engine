/**
 * A model-proposed Remark column must not be exported as verified source text
 * when the source location cannot be established. Its failure must not
 * delete an otherwise separately verified tender requirement.
 */
export function retainVerifiedRemark(input: {
  remark: string;
  requiresSourceLocation: boolean;
  hasSourceLocation: boolean;
}): { remark: string; omittedUnverified: boolean } {
  const remark = input.remark.trim();
  if (!remark) return { remark: "", omittedUnverified: false };
  if (input.requiresSourceLocation && !input.hasSourceLocation) {
    return { remark: "", omittedUnverified: true };
  }
  return { remark, omittedUnverified: false };
}
