import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const targets={datacenters:[{name:"DC1",folders:[{path:"/"},{path:"/RestoreTests"}],hosts:[{name:"esx01.example.local",datastores:[{name:"DS1",freeBytes:1e12},{name:"DS2",freeBytes:1e12}]}]}]};
test.beforeEach(async({page})=>{await page.route("**/api/recovery/vmware/targets",route=>route.fulfill({json:targets}));});
const recovery = {dispatchEnabled:false,sourceJobId:24,jobIds:[23,24],chain:[{jobId:23,job:"VMware-PNET",level:"Full",status:"Succeeded",media:[{name:"PNET-0009",status:"Append"}]}],items:[],blockers:[],unsupported:[],engineResolved:true,itemTotal:0,itemLimit:2000};
test("new VM review preserves safety, invalidates edits and guards unsaved close", async ({page}) => {
  await page.route(/\/api\/recovery\/\d+$/, route => route.fulfill({json:recovery}));
  const posted: Record<string, unknown>[] = [];
  await page.route("**/api/recovery/vmware/plan", async route => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({json:{state:"Review only",jobIds:[23,24],requiredMedia:["PNET-0009"],reviewDigest:"fixture",destination:posted[0].destination,blockers:["UUID compatibility requires verification.","Destination has not been verified against live vCenter."]}});
  });
  await page.goto("/?view=backups");
  await page.getByRole("button",{name:"Inspect recovery",exact:true}).first().click();
  const review = page.getByRole("button",{name:"Review VMware restore",exact:true});
  await expect(review).toBeVisible({timeout:45000}); await review.click();
  await expect(page.getByLabel("New VM name")).toBeFocused();
  await page.getByLabel("New VM name").fill("PNET-RESTORE-TEST");
  await page.getByLabel("Destination datacenter").selectOption("DC1");
  await page.getByLabel("Destination VM folder").selectOption("/RestoreTests");
  await page.getByLabel("Destination ESXi host").selectOption("esx01.example.local");
  await page.getByLabel("Destination datastore").selectOption("DS1");
  await review.click();
  await expect(page.getByText("Review only. No VM has been created or restored.")).toBeVisible();
  expect(posted[0].destination).toMatchObject({power:"off",network:"disconnected",overwrite:"Never"});
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  await page.screenshot({path:".local/vmware-restore-plan.png",fullPage:true});
  await page.getByLabel("Destination datastore").selectOption("DS2");
  await expect(page.getByText("Review only. No VM has been created or restored.")).toHaveCount(0);
  await page.getByRole("button",{name:"Close recovery inspection"}).click();
  await expect(page.getByRole("dialog",{name:"Discard unsaved changes?"})).toBeVisible();
  await page.getByRole("button",{name:"Go back",exact:true}).click();
  await expect(page.getByLabel("Destination datastore")).toHaveValue("DS2");
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:".local/vmware-restore-plan-mobile.png",fullPage:true});
  await page.keyboard.press("Escape");
  await page.getByRole("button",{name:"Discard changes",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Recovery inspection",exact:true})).toHaveCount(0);
});

test("VMware review failure preserves destination and supports retry", async ({page}) => {
  await page.route(/\/api\/recovery\/\d+$/, route => route.fulfill({json:recovery}));
  let count=0;
  await page.route("**/api/recovery/vmware/plan", route => {
    count++;
    return route.fulfill(count===1 ? {status:422,json:{detail:[{loc:["body","destination","folder"],msg:"Invalid path"}]}} : {status:502,json:{detail:"VMware restore review unavailable."}});
  });
  await page.goto("/?view=backups");
  await page.getByRole("button",{name:"Inspect recovery",exact:true}).first().click();
  for (const [label,value] of [["New VM name","PNET-RESTORE-TEST"],["Destination datacenter","DC1"],["Destination VM folder","/RestoreTests"],["Destination ESXi host","esx01.example.local"],["Destination datastore","DS1"]]) {if(label==="New VM name")await page.getByLabel(label).fill(value);else await page.getByLabel(label).selectOption(value);}
  await page.getByRole("button",{name:"Review VMware restore",exact:true}).click();
  await expect(page.getByLabel("Destination VM folder")).toBeFocused();
  await expect(page.getByLabel("Destination VM folder")).toHaveAttribute("aria-invalid","true");
  await page.getByLabel("Destination VM folder").selectOption("/RestoreTests");
  await page.getByRole("button",{name:"Review VMware restore",exact:true}).click();
  await expect(page.locator("#vmware-plan-error")).toContainText("VMware restore review unavailable.");
  await expect(page.getByLabel("New VM name")).toHaveValue("PNET-RESTORE-TEST");
  await expect(page.getByRole("button",{name:"Review VMware restore",exact:true})).toBeEnabled();
});

test("new VM confirmation retains request key after uncertain delivery",async({page})=>{
 await page.route(/\/api\/recovery\/\d+$/,route=>route.fulfill({json:recovery}));
 await page.route("**/api/recovery/vmware/plan",route=>route.fulfill({json:{dispatchEnabled:true,state:"Ready for confirmation",jobIds:[23,24],requiredMedia:["PNET-0009"],reviewDigest:"a".repeat(64),destination:route.request().postDataJSON().destination,blockers:[]}}));
 const requests:Record<string,unknown>[]=[];
 await page.route("**/api/recovery/vmware/restore",route=>{const body=route.request().postDataJSON();requests.push(body);return route.fulfill(requests.length===1?{status:503,json:{detail:"Delivery unknown; reconcile the operation journal."}}:{status:202,json:{id:"12345678-1234-1234-1234-123456789abc",kind:"restore",target:"24",state:"Prepared",parameters:{mode:"vmware-new-vm"}}});});
 await page.goto("/?view=backups");await page.getByRole("button",{name:"Inspect recovery",exact:true}).first().click();
 await page.getByLabel("New VM name").fill("PNET-RESTORE-TEST");
 await page.getByLabel("Destination datacenter").selectOption("DC1");await page.getByLabel("Destination VM folder").selectOption("/RestoreTests");await page.getByLabel("Destination ESXi host").selectOption("esx01.example.local");await page.getByLabel("Destination datastore").selectOption("DS1");
 await page.getByRole("button",{name:"Review VMware restore",exact:true}).click();await page.getByRole("button",{name:"Restore new VMware VM",exact:true}).click();
 const confirm=page.getByRole("dialog",{name:"Create and restore PNET-RESTORE-TEST?"});await expect(confirm.getByRole("button",{name:"Go back",exact:true})).toBeFocused();
 await confirm.getByRole("button",{name:"Create and restore VM",exact:true}).click();await expect(confirm.getByRole("alert")).toContainText("Delivery unknown");
 await confirm.getByRole("button",{name:"Create and restore VM",exact:true}).click();await expect(confirm).not.toBeVisible();
 expect(requests).toHaveLength(2);expect(requests[0].idempotency_key).toBe(requests[1].idempotency_key);expect(requests[0].destination).toMatchObject({power:"off",network:"disconnected",overwrite:"Never"});
});
