// Code-only render-logic checks with a small DOM stand-in. No browser is used;
// these checks do not claim a visual or browser compatibility verification.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const data = html.match(/<script id="demo-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script = html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
class Element {
  constructor(id) { this.id=id;this.value='';this.textContent='';this.events={};this._html=''; }
  set innerHTML(value) {
    this._html=value;
    if(['item','checkpoint','metric'].includes(this.id)) this.value=value.match(/value="(\d+)"/)?.[1]??'';
  }
  get innerHTML() { return this._html; }
  addEventListener(name, callback) { this.events[name]=callback; }
}
const elements = new Map();
const element = id => {if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
element('demo-data').textContent=data;
const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>[]},console});
new vm.Script(script).runInContext(context);
const cases=JSON.parse(data).scenes;
let rendered=0;
for(let s=0;s<cases.length;s++){
  vm.runInContext(`sceneIndex=${s};renderScene()`,context);
  assert.match(element('results').innerHTML,/Pass/);
  assert.match(element('results').innerHTML,/Fail/);
  for(let i=0;i<cases[s].cases[0].items.length;i++){
    element('item').value=String(i);element('item').events.change();
    const item=cases[s].cases[0].items[i];
    for(let c=0;c<item.checkpoints.length;c++){
      element('checkpoint').value=String(c);element('checkpoint').events.change();
      for(let m=0;m<item.checkpoints[c].metrics.length;m++){
        element('metric').value=String(m);element('metric').events.change();rendered++;
        assert.match(element('metric-chart').innerHTML,/<svg/);
        assert.match(element('grades-chart').innerHTML,/<svg/);
        for(const id of ['local-chart','grades-chart','metric-chart','results','evidence'])
          assert.doesNotMatch(element(id).innerHTML,/(?:NaN|undefined|Infinity)/,`${s}/${i}/${c}/${m}/${id}`);
        if(item.quantification.status==='complete')assert.match(element('local-chart').innerHTML,/<polyline|<circle/);
      }
    }
  }
}
assert.match(element('sensitivity-table').innerHTML,/22.39/);
console.log(`PASS: ${rendered} scene/item/checkpoint/metric selections; no invalid chart coordinates; complete reports and local traces rendered in code. Browser visuals NOT tested.`);
