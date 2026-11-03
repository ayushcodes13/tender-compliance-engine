import test from 'node:test';import assert from 'node:assert/strict';
import {nativeFontBold,nativeBoldPrefix,confirmedNativeHeadingPrefix} from './native-typography.ts';

test('recognizes explicit native font weights without guessing unknown face names',()=>{
 assert.equal(nativeFontBold('BCDFEE+TimesNewRomanPS-BoldMT'),true);
 assert.equal(nativeFontBold('Helvetica-Bold'),true);
 assert.equal(nativeFontBold('TimesNewRomanPS-BoldItalicMT'),true);
 assert.equal(nativeFontBold('TimesNewRomanPS-ItalicMT'),false);
 assert.equal(nativeFontBold('BCDEEE+TimesNewRomanPSMT'),false);
 assert.equal(nativeFontBold('Helvetica'),false);
 assert.equal(nativeFontBold('F1'),undefined);
 assert.equal(nativeFontBold('BlackbirdRegular'),undefined);
 assert.equal(nativeFontBold(undefined),undefined);
});
test('retains a literal bold title only when it precedes known regular body text',()=>{
 const items=[{str:'16.',bold:true},{str:'Source shutter assembly',bold:true},{str:'The system shall withstand 300 N.',bold:false}];
 assert.equal(nativeBoldPrefix(items),'16. Source shutter assembly');
 assert.equal(nativeBoldPrefix(items.slice(0,2)),null);
 assert.equal(nativeBoldPrefix([{str:'Title',bold:true},{str:'Unknown weight'}]),null);
 assert.equal(nativeBoldPrefix([{str:'a)',bold:true},{str:'Required material',bold:false}]),null);
 assert.equal(nativeBoldPrefix([{str:'300',bold:true},{str:'N capacity',bold:false}]),null);
});


test('an inline requirement title needs agreement between native style and literal model metadata',()=>{
 assert.equal(confirmedNativeHeadingPrefix('18. Computer package','requirement','18. Computer package'),'18. Computer package');
 assert.equal(confirmedNativeHeadingPrefix('18. Computer package','requirement','Computer package'),undefined);
 assert.equal(confirmedNativeHeadingPrefix(null,'requirement','18. Computer package'),undefined);
 assert.equal(confirmedNativeHeadingPrefix('16. Source shutter assembly','section',''),'16. Source shutter assembly');
});
