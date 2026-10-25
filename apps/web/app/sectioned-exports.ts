import { Document, HeadingLevel, Packer, Paragraph, Table, TableCell, TableRow, TextRun, WidthType } from 'docx';
import ExcelJS from 'exceljs';
import type { ResponseSheet } from './response-sheet.ts';
import { buildResponseSections } from './response-sections.ts';

export function createSectionedResponseDocument(sheet:ResponseSheet):Document {
  const content:Array<Paragraph|Table>=[];let previousAnnexure='';
  for(const section of buildResponseSections(sheet)){
    if(section.annexure!==previousAnnexure){
      content.push(new Paragraph({text:section.annexure,heading:HeadingLevel.HEADING_1,pageBreakBefore:Boolean(previousAnnexure),keepNext:true}));
      for(const line of section.titleLines)content.push(new Paragraph({text:line,keepNext:true,spacing:{after:100}}));
      previousAnnexure=section.annexure;
    }
    if(section.heading)content.push(new Paragraph({text:section.heading,heading:HeadingLevel.HEADING_2,keepNext:true}));
    const cell=(text:string,bold=false)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:text.replace(/\uF0B7/g,'•'),bold,size:20})]})],margins:{top:90,bottom:90,left:100,right:100}});
    const weights=section.columns.map(column=>column.role==='requirement'?3.8:1);const sum=weights.reduce((a,b)=>a+b,0)||1;
    content.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},columnWidths:weights.map(weight=>Math.floor(15440*weight/sum)),rows:[
      new TableRow({tableHeader:true,children:section.columns.map(column=>cell(column.header,true))}),
      ...section.rows.map(row=>new TableRow({cantSplit:true,children:row.values.map(value=>cell(value))})),
    ]}));
    content.push(new Paragraph({text:'',spacing:{after:100}}));
  }
  return new Document({styles:{default:{document:{run:{font:'Calibri',size:20,color:'000000'}}},paragraphStyles:[
    {id:'Heading1',name:'Heading 1',basedOn:'Normal',next:'Normal',run:{bold:true,size:28,color:'000000'},paragraph:{spacing:{before:120,after:160}}},
    {id:'Heading2',name:'Heading 2',basedOn:'Normal',next:'Normal',run:{bold:true,size:24,color:'000000'},paragraph:{spacing:{before:180,after:120}}},
  ]},sections:[{properties:{page:{size:{width:16840,height:11910},margin:{top:700,right:700,bottom:700,left:700}}},children:content}]});
}

export async function createSectionedDocxBlob(sheet:ResponseSheet):Promise<Blob>{return Packer.toBlob(createSectionedResponseDocument(sheet));}

export function createSectionedWorkbook(sheet:ResponseSheet):ExcelJS.Workbook {
  const workbook=new ExcelJS.Workbook();const worksheet=workbook.addWorksheet('Technical response');let previousAnnexure='';
  for(const section of buildResponseSections(sheet)){
    const count=section.columns.length;
    const addHeading=(text:string,size:number)=>{if(!text)return;const row=worksheet.addRow([text]);if(count>1)worksheet.mergeCells(row.number,1,row.number,count);row.font={bold:true,size,name:'Arial'};row.alignment={wrapText:true,vertical:'top'};row.height=24;};
    if(section.annexure!==previousAnnexure){addHeading(section.annexure,14);for(const line of section.titleLines)addHeading(line,11);previousAnnexure=section.annexure;}
    addHeading(section.heading,12);
    const header=worksheet.addRow(section.columns.map(column=>column.header));header.font={bold:true,name:'Arial',size:10};
    header.eachCell(cell=>{cell.fill={type:'pattern',pattern:'solid',fgColor:{argb:'FFEFF2F5'}};});
    for(const row of section.rows){const added=worksheet.addRow(row.values.map(value=>value.replace(/\uF0B7/g,'•')));added.alignment={wrapText:true,vertical:'top'};added.font={name:'Arial',size:10};added.height=Math.max(22,...row.values.map((value,index)=>value.split(/\r?\n/).reduce((sum,line)=>sum+Math.max(1,Math.ceil(line.length/(section.columns[index]?.role==='requirement'?78:26))),0)*14+8));}
    worksheet.addRow([]);
    section.columns.forEach((column,index)=>{worksheet.getColumn(index+1).width=column.role==='requirement'?78:26;});
  }
  worksheet.pageSetup={orientation:'landscape',fitToPage:true,fitToWidth:1,fitToHeight:0};
  return workbook;
}
