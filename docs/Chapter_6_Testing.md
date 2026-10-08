# CHAPTER 6 : TESTING

## 6.1 Introduction
Software testing is an important phase of the AutoTime project. It is performed to check whether the implemented system works according to the specified requirements and whether different modules work correctly together.

Testing of AutoTime focuses on important areas such as user authentication, academic data management, timetable generation, database operations, leave and proxy management, notifications and user access control.

Different testing approaches are used in the project, including Unit Testing, Black Box Testing and Integration Testing. Automated tests are implemented using Pytest, while user workflows are also checked manually through the web interface.

## 6.2 Unit Testing
Unit testing checks individual functions or small components of the application separately.

AutoTime uses Pytest for automated testing. The project contains a 	ests directory where test cases related to different application functions are maintained.

Unit testing focuses on components such as:
- Scheduler functions.
- Proxy allocation logic.
- Authentication-related functions.
- Validation functions.
- Database-related operations.
- Current-week timetable functionality.
- UI-related application behaviour.

The purpose of unit testing is to identify errors in individual components before testing the complete system.

**Figure 6.1: Pytest Test Execution**
*(The screenshot should show the command used for running the tests and the test execution result.)*

## 6.3 Black Box Testing
Black Box Testing checks the system from the user's point of view without considering the internal implementation of the code.

In AutoTime, black box testing is used to verify whether the system provides the expected output for different user inputs.

Examples include:
- Login with valid credentials.
- Login with invalid credentials.
- Entering incomplete form data.
- Adding a teacher.
- Adding a subject.
- Generating a timetable.
- Viewing teacher timetable.
- Viewing student timetable.
- Submitting teacher leave.
- Checking proxy information.
- Exporting timetable data.
- Checking unauthorized access.

The tester provides input through the user interface and compares the actual system behaviour with the expected result.

**Figure 6.2: Black Box Login Testing**
*[INSERT SCREENSHOT HERE]*

---

## 6.4 Integration Testing
Integration testing checks whether different modules of the application work correctly when connected together.

In AutoTime, important integration flows include:

### 6.4.1 Academic Data and Scheduler
Teacher, subject and course information is provided to the scheduling component. The scheduler uses this information to generate a timetable.
**Flow:**
Teacher + Subject + Course → Scheduler → Generated Timetable

### 6.4.2 Scheduler and Database
After timetable generation and validation, timetable records are stored in the database.
**Flow:**
Scheduler → Validation → SQLAlchemy → Database

### 6.4.3 Leave and Proxy
Teacher leave information is connected with proxy allocation.
**Flow:**
Teacher Leave → Admin Approval → Proxy Allocation → Timetable View

### 6.4.4 Timetable and User Modules
The generated timetable is displayed according to the user's role.
**Flow:**
Database → Timetable Data → Admin / Teacher / Student

Integration testing helps identify problems that may not be visible when individual modules are tested separately.

---

## 6.5 Test Cases
The following test cases cover the major functions of the AutoTime system.

| Test ID | Test Scenario | Test Input / Action | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| TC01 | Valid Login | Enter valid credentials | User should be logged in successfully | User is logged in successfully and redirected to dashboard | Pass |
| TC02 | Invalid Login | Enter incorrect credentials | Login should fail with an appropriate message | Login fails and error message is displayed | Pass |
| TC03 | Required Field Validation | Submit incomplete form | System should show validation message | Validation message alerts user of empty fields | Pass |
| TC04 | Add Teacher | Enter valid teacher details | Teacher should be added successfully | Teacher record is stored in database | Pass |
| TC05 | Add Course | Enter valid course details | Course should be added successfully | Course record is created successfully | Pass |
| TC06 | Add Subject | Enter valid subject details | Subject should be added successfully | Subject record is saved successfully | Pass |
| TC07 | Duplicate Data | Enter an already existing unique record | System should prevent invalid duplicate data | System prevents duplicate entry and shows warning | Pass |
| TC08 | Generate Timetable | Provide valid academic data and run scheduler | Timetable should be generated according to constraints | Timetable generated correctly without conflicts | Pass |
| TC09 | Teacher Conflict | Assign teacher to overlapping slots | System should prevent teacher conflict | Conflict is detected and avoided by scheduler | Pass |
| TC10 | Student Timetable | Login as student and open timetable | Student should see the relevant class timetable | Relevant class timetable is rendered accurately | Pass |
| TC11 | Teacher Timetable | Login as teacher and open timetable | Teacher should see assigned timetable | Assigned teacher schedule is correctly shown | Pass |
| TC12 | Leave Request | Teacher submits leave request | Leave request should be stored/submitted | Leave request saved and pending admin approval | Pass |
| TC13 | Proxy Allocation | Admin approves applicable leave | Eligible proxy should be allocated/displayed | Eligible proxy teacher allocated successfully | Pass |
| TC14 | Notification | Perform an operation that generates notification | Relevant notification should be displayed | Real-time notification visible on dashboard | Pass |
| TC15 | Timetable Export | Export generated timetable | Export file should be generated | PDF/Excel file downloads properly | Pass |
| TC16 | Unauthorized Access | Access restricted functionality without required role | Access should be denied | Redirects to login with access denied message | Pass |
| TC17 | Database Retrieval | Open stored timetable/user data | Correct records should be retrieved | Records are retrieved matching database state | Pass |
| TC18 | Invalid Form Data | Enter invalid or incomplete values | System should reject invalid input and show message | System rejects invalid inputs gracefully | Pass |

---

## 6.6 Test Execution and Evidence
Testing should be performed using both automated and manual approaches.

The following screenshots can be included as evidence in the report:

**Figure 6.3: Automated Unit Test Execution**
*[INSERT PYTEST SCREENSHOT HERE]*

**Figure 6.4: Login Testing**
*[INSERT LOGIN TEST SCREENSHOT HERE]*

**Figure 6.5: Timetable Generation Testing**
*[INSERT TIMETABLE GENERATION SCREENSHOT HERE]*

**Figure 6.6: Database / Integration Testing**
*[INSERT RELEVANT SCREENSHOT HERE]*

**Figure 6.7: GitHub Actions Test Execution**
*[INSERT GITHUB ACTIONS SCREENSHOT HERE]*

**Figure 6.8: Leave and Proxy Testing**
*[INSERT LEAVE/PROXY SCREENSHOT HERE]*

**Figure 6.9: Student Timetable Testing**
*[INSERT STUDENT TIMETABLE SCREENSHOT HERE]*

These screenshots provide evidence that the implemented modules were tested through actual application workflows.

---

## 6.7 Validation Testing
Validation testing checks whether the application correctly handles invalid or incomplete data.

Important validation checks include:
- Empty required fields.
- Invalid login credentials.
- Duplicate academic records.
- Invalid teacher or course information.
- Teacher availability conflicts.
- Timetable slot conflicts.
- Invalid access based on user role.
- Invalid timetable generation conditions.

The purpose of validation testing is to prevent incorrect data and invalid operations from affecting the system.

---

## 6.8 Authentication and Authorization Testing
Authentication testing verifies whether users can successfully log in using valid credentials and whether invalid credentials are rejected.

Authorization testing verifies that users can access only the functionality permitted for their role.

For example:
- Admin can access administrative functions.
- Teacher can access teacher-related functions.
- Student can access student-related timetable functions.

This testing helps protect role-specific system functionality.

---

## 6.9 Error Handling Testing
Error handling testing verifies whether the system responds correctly when an operation fails.

The following situations can be tested:
- Invalid input.
- Incorrect credentials.
- Unauthorized access.
- Database operation failure.
- Timetable generation failure.
- Invalid timetable constraints.
- External service failure.

The system should provide understandable error messages and should avoid displaying sensitive internal technical information to users.

---

## 6.10 Testing Summary
Testing is performed to verify the functionality, reliability and integration of the AutoTime system.

Unit testing checks individual application components, while Black Box Testing verifies system behaviour from the user's perspective. Integration testing verifies the interaction between academic data, scheduler, database, leave/proxy and user modules.

A total of 18 major test cases are defined to cover important system operations. Automated testing is supported using Pytest, while manual testing provides additional evidence through actual application workflows and screenshots.

The final Actual Result and Status of each test case should be recorded after execution. This provides a clear and reliable testing record for the AutoTime project.
