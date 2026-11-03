import {buildResponseSheet} from '../response-sheet.ts';
export const fixture=()=>buildResponseSheet({normalizedTables:true,requirements:[
  {id:'a-heading',text:'A. Optical Table',quote:'A. Optical Table',rowType:'section',page:20,sourceSectionTitle:'Annexure I',sourceSectionHeadings:['Technical Specifications for Optical Tables']},
  {id:'a',text:'≥ 300 mm',quote:'≥ 300 mm',page:20,sourceSectionTitle:'Annexure I',sourceSectionHeadings:['Technical Specifications for Optical Tables'],sourceColumnMap:[{header:'Specification',role:'heading'},{header:'Description',role:'specification'}],sourceCells:['Thickness','≥ 300 mm']},
  {id:'b-heading',text:'B. Isolators',quote:'B. Isolators',rowType:'section',page:21,sourceSectionTitle:'Annexure I'},
  {id:'b',text:'6 EA',quote:'6 EA',page:21,sourceSectionTitle:'Annexure I',sourceCells:['Quantity','6 EA']},
  {id:'ii-heading',text:'A. Optical Table',quote:'A. Optical Table',rowType:'section',page:23,sourceSectionTitle:'Annexure II'},
  {id:'ii',text:'±0.1 mm',quote:'±0.1 mm',page:23,sourceSectionTitle:'Annexure II',sourceCells:['Flatness','±0.1 mm']},
]});
