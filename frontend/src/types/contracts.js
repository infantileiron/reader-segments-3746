/** @typedef {{id:number,code:string,weekly_reading:number,completion:number,night_share:number,note:string}} Reader */
/** @typedef {{id:number,name:string,k:number,features:string[],state:string,week_start:string,week_end:string,entitlement_version:number,qualification:object,result:object}} Segment */
/** @typedef {{id:number,segment_id:number,cluster_id:number,title:string,note:string,members:string[],status:string,send_date:string,entitlement_version:number,entitlement_basis:object,approved_by:string,approved_at:string}} Outreach */
/** @typedef {{id:number,name:string,state:string,total_rows:number,accepted_rows:number,duplicate_rows:number,rejected_rows:number,superseded_rows:number,problem_rows:number,rejected:object[],entitlement_version:number,events:object[]}} Batch */
/** @typedef {{version:number,batch_id:number,checksum:string,members:number,ranges:number,created:string}} EntitlementVersion */
