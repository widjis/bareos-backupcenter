import {test,expect} from '@playwright/test';
const row={job:'VMware-PNET',timeWita:'21:30',automatic:true,retentionDays:30,maximumVolumes:6};
test('active policy is reviewed and unknown delivery is reconciled without resending',async({page})=>{
 let applied=false;let submits=0;let key='';
 await page.route('**/api/policies/active',route=>route.fulfill({json:{jobs:[{...row,timeWita:applied?'21:45':'21:30'}],applyEnabled:true}}));
 await page.route('**/api/policies/active/preview',route=>route.fulfill({json:{definition:route.request().postDataJSON().definition,reviewDigest:'a'.repeat(64),existingVolumePolicy:'Existing volume minima remain.',doesNotRun:'No backup or cleanup is run.'}}));
 await page.route('**/api/policies/active/apply',route=>{submits++;const body=route.request().postDataJSON();key=body.request_id;expect(body.definition).toMatchObject({jobs:['VMware-PNET'],time_wita:'21:45',retention_days:30,maximum_volumes:6});return route.fulfill({status:502,json:{detail:'Policy outcome unknown; check application status.'}});});
 await page.route('**/api/policies/active/status/*',route=>{expect(route.request().url()).toContain(key);applied=true;return route.fulfill({json:{state:'Applied'}});});
 await page.goto('/?view=settings');const panel=page.getByRole('region',{name:'Active backup schedule and retention'});
 await panel.getByLabel('VMware-PNET',{exact:true}).check();await panel.getByLabel('Backup start (WITA)').fill('21:45');await panel.getByRole('button',{name:'Review active policy',exact:true}).click();await panel.getByRole('button',{name:'Apply reviewed policy',exact:true}).click();
 const d=page.getByRole('dialog',{name:'Apply schedule and retention?'});await expect(d.getByRole('button',{name:'Go back',exact:true})).toBeFocused();await d.getByRole('button',{name:'Apply policy',exact:true}).click();await expect(panel.getByRole('alert')).toContainText('outcome unknown');await expect(panel.getByLabel('Backup start (WITA)')).toBeDisabled();
 await panel.getByRole('button',{name:'Check application status',exact:true}).click();await expect(panel).toContainText('Application status: Applied');await expect(panel.getByRole('alert')).toHaveCount(0);expect(submits).toBe(1);await expect(panel).toContainText('21:45 WITA');
 await page.screenshot({path:'.local/active-policy.png',fullPage:true});
 await page.getByRole('link',{name:'History',exact:true}).click();await expect(page.getByRole('heading',{name:'History',exact:true})).toBeVisible();
});
