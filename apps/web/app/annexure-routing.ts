type PositionedText = {text:string;box:{x:number;y:number;width:number;height:number}};

/** Header cells can be vertically aligned differently; use the earliest cell. */
export function sourceTableTextTop(rows:Array<{bbox:{y:number};cellBoxes:Array<{y:number}|null>}>):number {
  return rows.length ? Math.min(...rows.flatMap(row=>[row.bbox.y,...row.cellBoxes.flatMap(box=>box?[box.y]:[])])) : 0;
}

/** Only a standalone, visible top-of-page heading establishes an annexure boundary. */
export function findAnnexureHeading(items: PositionedText[], pageHeight: number): string | null {
  const lines: Array<{y:number;items:PositionedText[]}> = [];
  for(const item of items.filter(item=>item.text.trim()&&item.box.y<pageHeight*0.35).sort((a,b)=>a.box.y-b.box.y||a.box.x-b.box.x)) {
    const line=lines.find(line=>Math.abs(line.y-item.box.y)<3);
    if(line)line.items.push(item);else lines.push({y:item.box.y,items:[item]});
  }
  for(const line of lines){
    const text=line.items.sort((a,b)=>a.box.x-b.box.x).map(item=>item.text).join(' ').replace(/\s+/g,' ').trim();
    // Parentheses are part of some tenders' literal heading, not a body reference.
    const label = text.startsWith('(') && text.endsWith(')') ? text.slice(1,-1).trim() : text;
    if(/^Annexure\s*[-–—]?\s*(?:[IVXLCDM]+|[A-Z]|\d+)\s*$/i.test(label))return text;
  }
  return null;
}

/** A technical section title can label output without expanding routing to the document tail. */
export function findTechnicalSectionHeading(items: PositionedText[], pageHeight: number): string | null {
  const lines: Array<{y:number;items:PositionedText[]}> = [];
  for(const item of items.filter(item=>item.text.trim()&&item.box.y<pageHeight*0.75).sort((a,b)=>a.box.y-b.box.y||a.box.x-b.box.x)) {
    const line=lines.find(line=>Math.abs(line.y-item.box.y)<3);
    if(line)line.items.push(item);else lines.push({y:item.box.y,items:[item]});
  }
  for(const line of lines) {
    const text=line.items.sort((a,b)=>a.box.x-b.box.x).map(item=>item.text).join(' ').replace(/\s+/g,' ').trim();
    if(line.y<pageHeight*0.35&&/^Section\s*(?:\d+|[IVXLCDM]+)\s*[-–—:]\s*Technical\s+(?:specifications?|requirements?)\s*$/i.test(text))return text;
    if(/^Technical\s+(?:specifications?|requirements?)\s*:?$/i.test(text))return text;
  }
  return null;
}

/** Retain every page in selected source annexures, including non-technical-looking tails. */
export function expandSelectedAnnexures(selectedPages: number[], annexureStarts: number[], availablePages: number[]): number[] {
  const starts=[...new Set(annexureStarts)].sort((a,b)=>a-b);
  const selected=new Set(selectedPages);
  for(let index=0;index<starts.length;index++){
    const first=starts[index];const next=starts[index+1]??Infinity;
    if(!selectedPages.some(page=>page>=first&&page<next))continue;
    for(const page of availablePages)if(page>=first&&page<next)selected.add(page);
  }
  return [...selected].sort((a,b)=>a-b);
}

/** Preserve only literal source lines between the annexure label and its first table. */
export function sourceAnnexureTitleLines(items: PositionedText[], annexure: string, tableTop: number, sourceText: string): string[] {
  const normalize = (value: string) => value.replace(/\s+/g,' ').trim();
  const lines: Array<{y:number;items:PositionedText[]}> = [];
  for(const item of items.filter(item=>item.text.trim()&&item.box.y<tableTop).sort((a,b)=>a.box.y-b.box.y||a.box.x-b.box.x)) {
    const line=lines.find(line=>Math.abs(line.y-item.box.y)<3);
    if(line)line.items.push(item);else lines.push({y:item.box.y,items:[item]});
  }
  const textLines=lines.map(line=>normalize(line.items.sort((a,b)=>a.box.x-b.box.x).map(item=>item.text).join(' ')));
  const start=textLines.indexOf(normalize(annexure));
  if(start<0)return [];
  const native=normalize(sourceText);
  return textLines.slice(start+1).filter(text=>text&&native.includes(text));
}
