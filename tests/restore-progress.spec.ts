import {test,expect} from "@playwright/test";
const observed={jobId:27,active:true,status:"Running",phase:"Restoring disks",elapsedSeconds:10,bytes:0,files:0,errors:0,observedAt:"2026-10-15T07:41:00Z",lines:[{time:"2026-10-15T07:40:41Z",text:"Successfully created VM PNET-RESTORE-TEST"}]};
test.beforeEach(async({page})=>{await page.route("**/api/operations",route=>route.fulfill({json:{operations:[{id:"fixture",kind:"restore",target:"24",state:"Running",job_id:27,parameters:{destination:{vm_name:"PNET-RESTORE-NAMED"}}}]}}));});
test("restore progress updates to terminal warnings and stops polling",async({page})=>{
 let calls=0,finished=false;await page.route("**/api/sessions/27/progress",route=>{calls++;return route.fulfill({json:!finished?observed:{...observed,active:false,status:"Warning",phase:"Completed with warnings",bytes:16044756500,files:3,elapsedSeconds:89,warnings:[{kind:"identity-change",explanation:"A new identity was generated for the restored copy.",text:"Warning: UUID already exists; generated UUID"},{kind:"unclassified",explanation:"This warning needs review in the restore log.",text:"Warning: Read timeout"}]}});});
 await page.goto("/?view=history");const panel=page.getByRole("region",{name:"Restore progress Job 27"});
 await expect(panel.getByText("Restoring disks",{exact:false})).toBeVisible();await expect(panel).toContainText("percentage is unavailable");finished=true;
 await expect(panel).toContainText("Completed with warnings",{timeout:15000});await expect(panel).toContainText("14.94 GiB");
 const stoppedAt=calls;await page.waitForTimeout(3500);expect(calls).toBe(stoppedAt);
 await panel.getByText("Latest restore log",{exact:false}).click();await expect(panel.getByText("Successfully created VM PNET-RESTORE-TEST",{exact:true})).toBeVisible();
 await panel.getByText("Restored VM identity changed",{exact:true}).click();await expect(panel).toContainText("A new identity was generated");
 await panel.getByText("Warning needs review",{exact:true}).click();await expect(panel).toContainText("This warning needs review");
 await page.getByRole("button",{name:"PNET-RESTORE-NAMED",exact:true}).click();
 const drawer=page.getByRole("dialog",{name:"Job #27",exact:true});
 await expect(drawer.getByRole("heading",{name:"PNET-RESTORE-NAMED",exact:true})).toBeVisible();await expect(drawer).toContainText("Bareos job: RestoreFiles");
 await page.screenshot({path:".local/restore-progress.png",fullPage:true});
});
test("progress error retains last data and recovers on a read retry",async({page})=>{
 let errorNow=false,recovered=false;await page.route("**/api/sessions/27/progress",route=>{return route.fulfill(!errorNow?{json:observed}:!recovered?{status:502,json:{detail:"Progress temporarily unavailable."}}:{json:{...observed,active:false,status:"Succeeded",phase:"Completed"}});});
 await page.goto("/?view=history");const panel=page.getByRole("region",{name:"Restore progress Job 27"});await expect(panel).toContainText("Restoring disks");errorNow=true;await expect(panel).toContainText("Showing the last received values",{timeout:15000});await expect(panel).toContainText("Stale");
 recovered=true;await panel.getByRole("button",{name:"Retry progress"}).click();await expect(panel).toContainText("Session ended");await expect(panel.getByRole("alert")).toHaveCount(0);
});
