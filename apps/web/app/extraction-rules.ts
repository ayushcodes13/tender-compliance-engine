const obligationPattern = /\b(shall|must|should|required|minimum|maximum|not less than|not more than|at least|at most|comply with|conform to|provide|submit|specify|include|achieve|withstand|operate|measured|rated|capable of)\b/i;

// Keep the rule-based preview deliberately conservative: tender logistics,
// commercial terms and bid-process instructions are not technical specs.
const nonTechnicalPattern = /\b(?:price|prices|pricing|cost|costs|charges|quotation|quotations|quoted amount|commercial|financial bid|financial offer|tax(?:es)?|gst|currency|payment|payments|invoice|invoicing|turnover|net worth|earnest money|emd|bid security|bank guarantee|performance security|liquid assets|eligibility|eligible bidder|bidder qualification|registration|e-procurement|eprocurement|cpp portal|bid opening|tender opening|submission deadline|bid submission|tender submission|tender documents|annexure|declaration|undertaking|blacklist(?:ed|ing)?|contract award|letter of acceptance|cip|cif|fob|ex works|freight|shipping|shipment|dispatch|consignee|destination|delivery|delivered|take back|packing material|waste packing|supplier|vendor|bidder|bid process|participate in the bid|two envelopes|two bid system|second column|user list|brochure|technical specifications provided in the tender|indicate compliance|non-compliance|technical proposal|technical compliance table|technical evaluation|evaluation committee|warranty|warranties|maintenance|service support|service network|training|installation|commissioning|acceptance|liquidated damages|penalty|penalties|force majeure|dispute resolution|contract|contractor|agreement|order acceptance|purchase order|terms and conditions|license|licence|signature|authorized signatory|authorised signatory|undertaken|satisfaction|demonstrated)\b|\bsubmit(?:ted|ting)?\b.{0,100}\bthe tender\b/i;

const technicalPattern = /\b(?:technical specification|specification|specifications|equipment|instrument|device|machine|system|assembly|module|component|subsystem|motor|pump|valve|sensor|controller|processor|camera|lens|microscope|load cell|material|stainless steel|alloy|wavelength|frequency|voltage|current|power supply|power input|resolution|accuracy|precision|repeatability|measurement|measuring|range|capacity|throughput|sample rate|flow rate|pressure|temperature|humidity|tolerance|dimension|dimensions|size|weight|strength|interface|connector|protocol|signal|software|firmware|test(?:ing)?|calibration|performance|operating|operational|runtime|battery|enclosure|ip\s?\d{2}|emission|vibration|noise level|compatib(?:le|ility)|environmental|cooling|heating|load capacity|rated|kva|kw|kwh|rpm|mm|cm|inch(?:es)?|micron|µm|hz|mhz|ghz|vdc|vac|amp(?:s|ere)?|°c|°f|bar|pa|mpa|l\/min|ml\/min|gb|mbps|db)\b/i;
const quantifiedTechnicalPattern = /(?:\b\d+(?:[.,]\d+)?\s*%|\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m|inch(?:es)?|micron|µm|nm|hz|khz|mhz|ghz|vdc|vac|kw|kva|w|mw|a|ma|rpm|°c|°f|bar|pa|kpa|mpa|n|kn|n\/mm|kn\/mm|kg|g|l\/min|ml\/min|gb|mbps|db|cycles?)\b)/i;

// The model path already classifies technical and documentary obligations.
// Only procurement/commercial instructions that are unambiguous on their own
// may be hard-rejected here. A catalogue, certificate, inspection, quality,
// or installation clause can be a real tender requirement: source-verify it
// and leave it for the existing human-review workflow instead of deleting it.
// A matching source quote is still mandatory; this does not trust model output.
const clearlyAdministrativePattern = /\b(?:financial bid|price bid|price quotation|quoted price|contract value|earnest money deposit|emd|bid security|bank guarantee|turnover|net worth|eligible bidder|bidder qualification|tender submission deadline|bid opening|e-procurement portal|cpp portal|payment terms|invoice|gst|liquidated damages|penalty|delivery schedule|delivery location|shipping|freight|packing material|packing and dispatch|commercial offer|financial offer|blacklist(?:ed|ing)?|pre[- ]?dispatch inspection prior to packing|indicate compliance(?: status)?|compliance status \(?yes\s*\/\s*no\)?|comply \(?yes\s*\/\s*no\)? for each and every point|(?:must|to) be filled by the bidder|all points indicated above|points indicated above|(?:technical )?compliance report as prescribed in annexure)\b/i;

export function isClearlyAdministrativeClause(value: string): boolean {
  return clearlyAdministrativePattern.test(value);
}

/**
 * Keep obligation-shaped text or quantified product specs. Reject commercial,
 * logistics, and tender-process clauses.
 * This filter is a conservative review aid, not an exhaustive classifier.
 */
export function isTechnicalRequirementCandidate(value: string): boolean {
  if (nonTechnicalPattern.test(value)) return false;
  return technicalPattern.test(value) && (obligationPattern.test(value) || quantifiedTechnicalPattern.test(value));
}

export function splitTechnicalCandidates(value: string): string[] {
  return value.replace(/(^|\s)(?:\(?\d{1,2}[.)]|[•●▪])\s+/g, "$1")
    .split(/\n+|(?<=[!?])\s+|(?<=\.)\s+(?=[A-Z][a-z]{2,}\b)|;\s+|(?=\s+[a-z]\)\s+)/)
    .map((part) => part.replace(/^(?:[•●▪]|\(?\d{1,2}[.)]|[A-Za-z][.)])\s+/, "").replace(/\s+/g, " ").trim())
    .filter(Boolean);
}
