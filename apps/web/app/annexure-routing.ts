type PositionedText = {text:string;box:{x:number;y:number;width:number;height:number}};

/** Only a standalone, visible top-of-page heading establishes an annexure boundary. */
export function findAnnexureHeading(items: PositionedText[], pageHeight: number): string | null {
  const lines: Array<{y:number;items:PositionedText[]}> = [];
  for(const item of items.filter(item=>item.text.trim()&&item.box.y<pageHeight*0.35).sort((a,b)=>a.box.y-b.box.y||a.box.x-b.box.x)) {
    const line=lines.find(line=>Math.abs(line.y-item.box.y)<3);
    if(line)line.items.push(item);else lines.push({y:item.box.y,items:[item]});
  }
  for(const line of lines){
    const text=line.items.sort((a,b)=>a.box.x-b.box.x).map(item=>item.text).join(' ').replace(/\s+/g,' ').trim();
    if(/^Annexure\s*[-–—]?\s*(?:[IVXLCDM]+|[A-Z]|\d+)\s*$/i.test(text))return text;
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
