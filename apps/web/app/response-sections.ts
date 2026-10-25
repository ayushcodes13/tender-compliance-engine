import type { ResponseSheet, ResponseSheetColumn, ResponseSheetRow } from './response-sheet.ts';

export type ResponseSection = {
  id:string;
  annexure:string;
  titleLines:string[];
  heading:string;
  headingId?:string;
  columns:ResponseSheetColumn[];
  columnIndices:number[];
  rows:ResponseSheetRow[];
};

/** Shared UI/print projection. Source context becomes headings, not table data. */
export function buildResponseSections(sheet:ResponseSheet, includeCitations=false):ResponseSection[] {
  const sectioned=sheet.layout==='sectioned';
  const headingIndex=sheet.columns.findIndex(column=>column.role==='heading');
  const generatedHeadingIndex=!sectioned&&headingIndex>=0&&sheet.columns[headingIndex].sourceIndex===undefined ? headingIndex : -1;
  const annexureIndex=sectioned ? 1 : -1;
  const indices=sheet.columns.flatMap((column,index)=>
    (sectioned&&index===headingIndex)||index===generatedHeadingIndex||index===annexureIndex||(!includeCitations&&column.role==='page')?[]:[index]);
  const sections:ResponseSection[]=[];
  let sourceHeading="";let sourceHeadingId:string|undefined;
  for(const row of sheet.rows){
    if(!sectioned&&row.section){
      sourceHeading=(headingIndex>=0?row.values[headingIndex]:"")||row.values.find(Boolean)||"";
      sourceHeadingId=row.id;
      continue;
    }
    const annexure=annexureIndex>=0 ? row.values[annexureIndex]??'' : '';
    const heading=sectioned&&headingIndex>=0 ? row.values[headingIndex]??'' : sourceHeading;
    const headingId=sectioned?row.headingId:sourceHeadingId;
    let current=sections.at(-1);
    if(!current||current.annexure!==annexure||current.heading!==heading||current.headingId!==headingId){
      current={id:row.id,annexure,heading,headingId,titleLines:row.sectionHeadings??[],columns:indices.map(index=>({...sheet.columns[index],header:row.sourceHeaders?.[index]||sheet.columns[index].header})),columnIndices:indices,rows:[]};
      sections.push(current);
    }
    current.rows.push({...row,values:indices.map(index=>row.values[index]??'')});
  }
  return sections;
}
