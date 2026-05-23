import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from src.app.database import async_session_maker
from src.app.models.form_type import FormType
from src.app.models.form_record import FormRecord

async def main():
    async with async_session_maker() as db:
        # Get the first form type
        result = await db.execute(select(FormType).limit(1))
        ft = result.scalar_one_or_none()
        if not ft:
            print("No form type found to seed workflow data")
            return
            
        print(f"Seeding workflow data for Form Type: {ft.form_name}")
        
        # Department-routed workflow engine data
        ft.workflow_data = {
            "states": ["Draft", "Pending Manager", "Pending Reviewer", "Completed", "Cancelled"],
            "initial": "Draft",
            "transitions": [
                {
                    "trigger": "submit", 
                    "source": "Draft", 
                    "dest": "Pending Manager",
                    "assignment": {"role": "Manager", "department": "SAME_AS_CREATOR"}
                },
                {
                    "trigger": "verify", 
                    "source": "Pending Manager", 
                    "dest": "Pending Reviewer",
                    "assignment": {"role": "Reviewer", "department": "ANY"}
                },
                {
                    "trigger": "amend", 
                    "source": "Pending Reviewer", 
                    "dest": "Completed"
                },
                {
                    "trigger": "reject", 
                    "source": ["Pending Manager", "Pending Reviewer"], 
                    "dest": "Draft"
                }
            ]
        }
        await db.commit()
        print("Workflow seeded successfully!")
        
        # # Try to find a draft record to test available actions
        # rec_res = await db.execute(select(FormRecord).where(FormRecord.status == "Draft").limit(1))
        # record = rec_res.scalar_one_or_none()
        
        # if record:
        #     from src.app.services.form_record_service import FormRecordService
        #     svc = FormRecordService(db)
            
        #     # Simulate a worker in IT
        #     worker_data = {"user_id": "u1", "roles": ["worker"], "department": "IT"}
        #     actions = await svc.get_available_actions(record.record_id, worker_data)
        #     print(f"Draft Available Actions for Worker: {actions}")
            
        #     # Transition
        #     await svc.process_transition(record.record_id, "submit", worker_data)
        #     await db.refresh(record)
        #     print(f"After submit -> Status: {record.status}, Assigned Role: {record.assigned_role}, Assigned Dept: {record.assigned_department}")

        #     # Simulate an HR Manager trying to access it
        #     hr_manager_data = {"user_id": "u2", "roles": ["Manager"], "department": "HR"}
        #     hr_actions = await svc.get_available_actions(record.record_id, hr_manager_data)
        #     print(f"Actions for HR Manager: {hr_actions}")

        #     # Simulate an IT Manager trying to access it
        #     it_manager_data = {"user_id": "u3", "roles": ["Manager"], "department": "IT"}
        #     it_actions = await svc.get_available_actions(record.record_id, it_manager_data)
        #     print(f"Actions for IT Manager: {it_actions}")
            
        #     if "verify" in it_actions:
        #          await svc.process_transition(record.record_id, "verify", it_manager_data)
        #          await db.refresh(record)
        #          print(f"After verify -> Status: {record.status}, Assigned Role: {record.assigned_role}, Assigned Dept: {record.assigned_department}")
            
if __name__ == "__main__":
    asyncio.run(main())
