/** Unknown font metadata stays unknown; only explicit PostScript styles are used. */
export function nativeFontBold(name:unknown):boolean|undefined {
  if(typeof name!=='string'||!name)return undefined;
  if(/(?:^|[-+,\s])(?:bold|demi(?:bold)?|semi[- ]?bold|black|heavy)(?:italic|oblique)?(?:mt|ps)?$/i.test(name))return true;
  if(/bold|black|heavy|demi|semi/i.test(name))return undefined;
  if(/(?:regular|normal|roman|book|light|medium|psmt)$/i.test(name)||/(?:italic|oblique)(?:mt|ps)?$/i.test(name)
    || /(?:^|\+)(?:Helvetica|Arial|Courier)$/i.test(name)
    || /(?:Arial|Calibri|Tahoma|Verdana)MT$/i.test(name))return false;
  return undefined;
}

/** Returns a literal leading bold run only when known regular text follows. */
export function nativeBoldPrefix(items:Array<{str:string;bold?:boolean}>):string|null {
  const words=items.filter(item=>item.str.trim());
  const boundary=words.findIndex(item=>item.bold!==true);
  if(boundary<=0||words[boundary].bold!==false)return null;
  const prefix=words.slice(0,boundary).map(item=>item.str).join(' ').replace(/\s+/g,' ').trim();
  if(!/\p{L}/u.test(prefix)||/^[a-z][.)]$/i.test(prefix))return null;
  return prefix;
}

/** A requirement row also needs an agreeing literal model prefix to start a group. */
export function confirmedNativeHeadingPrefix(prefix:string|null|undefined,kind:string|undefined,modelPrefix:unknown):string|undefined {
  if(!prefix)return undefined;
  if(kind==='section'||kind==='optional_heading')return prefix;
  if(kind==='requirement'&&typeof modelPrefix==='string'&&modelPrefix.replace(/\s+/g,' ').trim()===prefix)return prefix;
  return undefined;
}
